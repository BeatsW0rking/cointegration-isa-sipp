"""Pin BLAS/OpenMP to one thread per process. Import this before numpy anywhere a process pool
is used: the sweep parallelises across processes, and multithreaded BLAS in every worker
oversubscribes the cores (observed 10x slowdown on the hourly screen)."""

import os

for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_var, "1")
