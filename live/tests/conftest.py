"""One maths thread for every test: with little free memory, OpenBLAS's default per-thread buffers fail to allocate and pytest dies silently."""
import os

for _v in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ.setdefault(_v, '1')
