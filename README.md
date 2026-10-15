# N-Queens Solver Benchmark Suite

So sánh hiệu năng giải bài toán N-Queens bằng **7 phương pháp** khác nhau, bao gồm 3 kiểu mã hóa SAT và 4 solver tối ưu hóa.

## Các phương pháp

### SAT Encoding (sử dụng PySAT + Glucose3)
| File | Mô tả | Độ phức tạp mã hóa |
|------|--------|---------------------|
| `binomial.py` | Mã hóa Binomial (Pairwise) – mỗi cặp biến tạo 1 mệnh đề | O(n²) clauses/constraint |
| `binary.py` | Mã hóa Binary – sử dụng biến phụ kiểu nhị phân | O(n·log n) clauses |
| `sequential.py` | Mã hóa Sequential Counter (Sinz 2005) – chuỗi thanh ghi tuần tự | O(n) clauses/constraint |

### Optimization Solvers
| File | Solver | Loại |
|------|--------|------|
| `cplex_cp.py` | IBM CPLEX CP Optimizer (`docplex.cp`) | Constraint Programming |
| `cplex_mip.py` | IBM CPLEX MIP (`docplex.mp`) | Mixed Integer Programming |
| `gurobi_mip.py` | Gurobi (`gurobipy`) | Mixed Integer Programming |
| `cpsat.py` | Google OR-Tools CP-SAT (`ortools`) | Hybrid CP-SAT |

## Cài đặt

```bash
# Bắt buộc (cho SAT solvers)
pip install python-sat

# OR-Tools (miễn phí, khuyến nghị)
pip install ortools

# CPLEX (cần license)
pip install docplex cplex

# Gurobi (cần license)
pip install gurobipy

# Trực quan hóa
pip install matplotlib
```

## Sử dụng Benchmark

Script chính là `benchmark_v2.py` (mỗi lần chạy nằm trong một process riêng, có timeout).

```bash
pip install psutil          # để đo bộ nhớ

# Chạy nhanh (N = 8, 16, 32; 2 lần lặp; timeout 20 s)
python benchmark_v2.py --quick

# Cấu hình dùng trong báo cáo: 12 giá trị N, 5 lần lặp, timeout 120 s,
# mỗi solver chạy với 1 thread và với số thread tự động (0)
python benchmark_v2.py --timeout 120 --repeats 5 --threads 1 0

# Tùy chỉnh
python benchmark_v2.py --n 100 200 500 --solvers SAT-Binary CPLEX-CP --repeats 5 --timeout 300
```

Tuỳ chọn chính: `--n`, `--solvers` (SAT-Binomial, SAT-Binary, SAT-Sequential, CPLEX-CP, CPLEX-MIP, Gurobi-MIP, CP-SAT), `--timeout`, `--repeats`, `--threads`, `--randomize-phases`, `--quick`, `--output-dir`.

### Kết quả đầu ra
- `benchmark_v2_runs_<thời gian>.csv`: mỗi dòng là một lần chạy (Import_s, Build_s, Solve_s, Total_s, PeakMB, Conflicts, Decisions, ...)
- `benchmark_v2_summary_<thời gian>.csv`: median / mean / std / min / max cho từng (N, solver, số thread)
- `benchmark_v2_plot_<thời gian>.png`: biểu đồ thời gian trung vị (log-log)
- `benchmark_v2_env_<thời gian>.json`: thông tin máy và phiên bản thư viện

Kết quả dùng trong báo cáo: `benchmark_v2_*_20261015_131718.*`.

## Chạy từng solver riêng lẻ

```bash
python binomial.py
python binary.py
python sequential.py
python cpsat.py
python cplex_cp.py
python cplex_mip.py
python gurobi_mip.py
```
