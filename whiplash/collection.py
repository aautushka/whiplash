import logging
import os
from collections import defaultdict
from typing import Optional

import numpy as np
from xxhash import xxh64

from whiplash.collection_config import CollectionConfig
from whiplash.hashing import vector_plane_hash
from whiplash.storage import DynamoStorage
from whiplash.vector import CompVector, Vector
from whiplash.vector_math import cosine_similarity, cosine_similarity_bulk

MAX_ITEMS_PER_BUCKET = int(os.environ.get("MAX_ITEMS_PER_BUCKET", 10000))

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class Collection:
    """A collection of vectors with LSH indexing and retrieval"""

    def __init__(
        self,
        config: CollectionConfig,
    ):
        self.collection_id = config.id
        storage = DynamoStorage(config.region)
        self.vector_table = storage.get_table(f"{self.collection_id}_vectors")
        self.bucket_table = storage.get_table(f"{self.collection_id}_buckets")
        self.config = config

    def __repr__(self) -> str:
        return f"Collection(collection_id={self.collection_id}, config={self.config})"

    def to_dict(self):
        return self.config.to_dict()

    @staticmethod
    def from_dict(data: dict):
        return Collection(CollectionConfig.from_dict(data))

    def hash_key(self, vector: np.ndarray, plane_id: int) -> str:
        """Compute the hash code for a vector and plane"""
        if not self.config.uniform_planes:
            raise ValueError("Uniform planes must be created before hashing")
        if plane_id not in self.config.uniform_planes:
            raise ValueError(f"Uniform plane with id not found: {plane_id}")
        # Project the vector onto all random hyperplanes
        return vector_plane_hash(vector, self.config.uniform_planes[plane_id])

    def create(self):
        """Create the collection"""
        self.vector_table.create_table()
        self.bucket_table.create_table()

    def get_item(self, id: str) -> Vector:
        """Get a single vector by id"""
        item = self.vector_table.get(id)
        if not item:
            raise ValueError(f"Vector with id not found: {id}")
        return Vector.from_dynamo(item)

    def get_bulk_items(self, ids: list[str]) -> list[Vector]:
        """Get a list of vectors by id"""
        data = self.vector_table.get_bulk(ids)
        return [Vector.from_dynamo(item) for item in data]

    def insert(self, vector: Vector) -> None:
        """Insert a vector into the collection"""
        if not self.config.uniform_planes:
            raise ValueError("Uniform planes must be created before inserting")

        self.vector_table.put(vector.to_dynamo())
        for plane_id in self.config.uniform_planes.keys():
            bucket_key = self.hash_key(vector.vector, plane_id)
            self.bucket_table.update_column(bucket_key, "ids", vector.id)

    def insert_batch(
        self, vectors: list[Vector], metadata=Optional[list[dict]]
    ) -> None:
        if not self.config.uniform_planes:
            raise ValueError("Uniform planes must be created before inserting")

        print("inserting vectors into the database")
        self.vector_table.put_batch([x.to_dynamo() for x in vectors])

        buckets = defaultdict(set)
        for vec in vectors:
            for plane_id in self.config.uniform_planes.keys():
                bucket_key = self.hash_key(vec.vector, plane_id)
                buckets[bucket_key].add(vec.id)

        print(f"number of buckets {len(buckets.keys())}")
        print(
            sorted([(len(v), k) for k, v in dict(buckets).items()], reverse=True)[:100]
        )

        for idx, (bucket, ids) in enumerate(dict(buckets).items()):
            print(f"update bucket {idx} / {len(buckets.keys())}")
            self.bucket_table.table.update_item(
                Key={"id": bucket},
                UpdateExpression=f"ADD ids :val",
                ExpressionAttributeValues={":val": ids},
            )

    def insert_metadata(self, metadata: dict[str, dict]) -> None:
        items = [{**v, "id": f"meta#{k}"} for k, v in metadata.items()]
        self.vector_table.put_batch(items)

    def search(self, query: np.ndarray, k: int = 5) -> list[CompVector]:
        """Search for the k closest vectors to the query vector"""
        if not self.config.uniform_planes:
            raise ValueError("Uniform planes must be created before searching")

        candidate_ids = set()
        bucket_keys = [
            self.hash_key(query, plane_id)
            for plane_id in self.config.uniform_planes.keys()
        ]

        buckets = self.bucket_table.get_batch(bucket_keys)
        # Merge all the buckets "ids" lists
        candidate_ids = {cid for bucket in buckets for cid in bucket.get("ids", set())}
        lookup_items = self.get_bulk_items(list(candidate_ids))
        logger.debug("Compared against N vectors:", len(lookup_items))
        if len(lookup_items) == 0:
            return []

        closest_indices = cosine_similarity_bulk(
            query, [item.vector for item in lookup_items], k
        )

        candidates = [
            CompVector(
                id=lookup_items[i].id,
                vector=lookup_items[i].vector,
                dist=cosine_similarity(query, lookup_items[i].vector),
            )
            for i in closest_indices
        ]
        candidates.sort(key=lambda x: x.dist, reverse=True)
        return candidates

    def search_with_metadata(self, query: np.ndarray, k: int = 5) -> list[dict]:
        found = self.search(query, k)
        ids = [f"meta#{x.id}" for x in found]

        metadata = self.vector_table.get_bulk(ids)

        joined = {
            x.id: {k: v for k, v in x.to_dict().items() if k != "vector"} for x in found
        }
        for meta in metadata:
            vector_id = meta["id"][len("meta#") :]
            joined[vector_id]["metadata"] = meta["metadata"]

        return [x for x in joined.values() if "metadata" in x]
