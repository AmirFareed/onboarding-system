# Phase 15C Queue Benchmark

Controlled processor: 10 ms per document, no OCR or AI calls. PostgreSQL queue,
row-lock claiming, and `drain_queue()` were used for every run.

| Documents | Workers | Time (s) | Docs/min | Avg queue wait (s) | Utilization | Retries | Failures |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 1 | 0.5372 | 1116.92 | 0.2964 | 18.62% | 0 | 0 |
| 10 | 2 | 0.2984 | 2010.51 | 0.1386 | 16.75% | 0 | 0 |
| 10 | 3 | 0.3011 | 1992.83 | 0.1475 | 11.07% | 0 | 0 |
| 40 | 1 | 1.9279 | 1244.90 | 0.9911 | 20.75% | 0 | 0 |
| 40 | 2 | 1.1762 | 2040.53 | 0.6062 | 17.00% | 0 | 0 |
| 40 | 3 | 1.0495 | 2286.75 | 0.4946 | 12.70% | 0 | 0 |
| 80 | 1 | 3.8222 | 1255.83 | 1.9495 | 20.93% | 0 | 0 |
| 80 | 2 | 3.1756 | 1511.51 | 1.5956 | 12.60% | 0 | 0 |
| 80 | 3 | 2.4229 | 1981.12 | 1.2999 | 11.01% | 0 | 0 |

The 80-document run completed with no duplicate processing, retries, or
failures. Worker count remains bounded by configuration; the benchmark does
not invoke OCR, Qwen, or VLM resources.
