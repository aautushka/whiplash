import os
import random
import time

from whiplash.api.client import Whiplash
from whiplash.api.client.vector import Vector

API_KEY = os.environ.get("WHIPLASH_API_KEY", "")
API_URL = os.environ.get("WHIPLASH_API_URL", "")


whiplash = Whiplash(
    API_URL,
    API_KEY,
)

dims = 1536


def random_vector():
    vector = Vector(
        f"id_{random.randint(100,99999999)}", [random.random() for _ in range(dims)]
    )
    return vector


print("retrieving collection")
start = time.time()
collection = whiplash.get_collection(f"example-{dims}")
print(f"took {time.time() - start}")

if not collection:
    print("creating collection")
    start = time.time()
    collection = whiplash.create_collection(
        f"example-{dims}", n_features=dims, n_planes=2, bit_start=10, bit_scale_factor=4
    )
    print(f"took {time.time() - start}")

    print("retrieving collection")
    start = time.time()
    collection = whiplash.get_collection(f"example-{dims}")
    print(f"took {time.time() - start}")

assert collection is not None

print(collection)

start = time.time()
batch_size = 1
vectors = [random_vector() for _ in range(batch_size)]

collection.insert_batch(vectors)
insert_time = (time.time() - start) / batch_size

print(f"Inserted {len(vectors)} vectors")
print(f"Average Insert time: {insert_time}")

start = time.time()
print(collection.search(random_vector().vector))
print("Random search took", time.time() - start, "seconds")

start = time.time()
print(collection.search(vectors[0].vector))
print("Exact search took", time.time() - start, "seconds")
