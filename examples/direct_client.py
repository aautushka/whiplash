import os
import random

import numpy as np

from whiplash import Vector, Whiplash


def random_vector():
    vector = Vector(
        f"id_{random.randint(100,99999999)}",
        np.array([random.random() for _ in range(n_features)]),
    )
    return vector


region = os.environ.get("AWS_REGION") or "eu-central-1"
os.environ["AWS_REGION"] = region

# AWS_PROFILE must be set in environment variables for boto3
whiplash = Whiplash(region, "dev")

# First time only setup
try:
    whiplash.setup()
except:
    # metadata table already exists
    pass

n_features = 1536

try:
    collection = whiplash.get_collection(f"example-{n_features}")
except:
    collection = None

if not collection:
    collection = whiplash.create_collection(
        f"example-{n_features}",
        n_features=n_features,
        n_planes=1,
        bit_start=20,
        bit_scale_factor=2,
    )

assert collection

vectors = [random_vector() for _ in range(1)]

for vec in vectors:
    collection.insert(vec)

result = collection.search(random_vector().vector)
print(f"found random: {result}")

result = collection.search(vectors[0].vector)
print(f"found exact: {result}")
