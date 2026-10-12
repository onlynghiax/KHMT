"""
N-Queens solver using IBM CPLEX CP Optimizer (docplex.cp).
"""
import os
import glob


def _find_cpoptimizer():
    """Auto-detect cpoptimizer.exe and add CPLEX bin dirs to PATH."""
    base_patterns = [
        r"C:\Program Files\IBM\ILOG\CPLEX_Studio*",
        r"C:\Program Files (x86)\IBM\ILOG\CPLEX_Studio*",
    ]
    for pattern in base_patterns:
        matches = sorted(glob.glob(pattern), reverse=True)  # newest first
        for studio_dir in matches:
            cpopt_exe = os.path.join(studio_dir, "cpoptimizer", "bin", "x64_win64", "cpoptimizer.exe")
            if os.path.isfile(cpopt_exe):
                # Also add CPLEX bin dir to PATH so cpoptimizer can find cplex DLL
                cplex_bin = os.path.join(studio_dir, "cplex", "bin", "x64_win64")
                cpopt_bin = os.path.join(studio_dir, "cpoptimizer", "bin", "x64_win64")
                current_path = os.environ.get("PATH", "")
                for d in [cplex_bin, cpopt_bin]:
                    if os.path.isdir(d) and d not in current_path:
                        os.environ["PATH"] = d + os.pathsep + current_path
                        current_path = os.environ["PATH"]
                return cpopt_exe
    return None


def solve_n_queens(n, timeout=300):
    """
    Solve the N-Queens problem using CPLEX CP Optimizer.
    
    Args:
        n (int): Board size / number of queens
        timeout (int): Timeout in seconds
        
    Returns:
        list: n x n board of 0/1, or None if no solution found
    """
    try:
        from docplex.cp.model import CpoModel
    except ImportError:
        print("docplex is not installed. Please install it using 'pip install docplex'.")
        return None
    
    # Create the model
    model = CpoModel(name=f'NQueens-{n}')
    
    # Integer variables: queen[i] represents the column of the queen in row i
    queens = [model.integer_var(0, n - 1, name=f'q{i}') for i in range(n)]
    
    # Constraints
    # No two queens in the same column
    model.add(model.all_diff(queens))
    # No two queens on the same main diagonal
    model.add(model.all_diff([queens[i] + i for i in range(n)]))
    # No two queens on the same anti-diagonal
    model.add(model.all_diff([queens[i] - i for i in range(n)]))
    
    # Auto-detect and configure cpoptimizer executable path
    cpopt_exe = _find_cpoptimizer()
    solve_kwargs = dict(TimeLimit=timeout, LogVerbosity='Quiet')
    if cpopt_exe:
        solve_kwargs['execfile'] = cpopt_exe
    
    # Solve the model
    try:
        result = model.solve(**solve_kwargs)
    except Exception as e:
        print(f"CPLEX CP solve error: {e}")
        return None
    
    if result and result.is_solution():
        board = [[0] * n for _ in range(n)]
        for i in range(n):
            col = result.get_value(queens[i])
            board[i][col] = 1
        return board
    else:
        return None

def print_solution(solution):
    """
    Print the solution board.
    
    Args:
        solution (list): n x n board of 0/1
    """
    if solution is None:
        print("No solution found.")
        return
        
    for row in solution:
        print(" ".join("Q" if cell else "." for cell in row))
    print()

if __name__ == '__main__':
    n = 8
    print(f"Solving N-Queens for N={n} using CPLEX CP Optimizer...")
    solution = solve_n_queens(n)
    if solution:
        print("Solution found:")
        print_solution(solution)
    else:
        print("No solution found.")
