"""
N-Queens solver using Google OR-Tools CP-SAT.
"""

def solve_n_queens(n, timeout=300):
    """
    Solves the N-Queens problem using OR-Tools CP-SAT solver.
    Returns an n x n 2D array (list of lists) with 1s for queens and 0s otherwise.
    Returns None if no solution is found or if ortools is not installed.
    """
    try:
        from ortools.sat.python import cp_model
    except ImportError:
        print("ortools not installed. Please install using: pip install ortools")
        return None

    model = cp_model.CpModel()
    
    # queens[i] represents the column position of the queen in row i
    queens = [model.new_int_var(0, n - 1, f'q{i}') for i in range(n)]
    
    # No two queens can share the same column
    model.add_all_different(queens)
    
    # No two queens can share the same diagonal
    model.add_all_different([queens[i] + i for i in range(n)])
    
    # No two queens can share the same anti-diagonal
    model.add_all_different([queens[i] - i for i in range(n)])
    
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = timeout
    solver.parameters.num_workers = 1  # For fair benchmarking
    
    status = solver.solve(model)
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        # Create n x n board
        board = [[0] * n for _ in range(n)]
        for i in range(n):
            col = solver.value(queens[i])
            board[i][col] = 1
        return board
    return None

def print_solution(solution):
    """
    Prints the N-Queens solution.
    """
    if not solution:
        print("No solution found or timeout occurred.")
        return
        
    for row in solution:
        print(" ".join("Q" if cell else "." for cell in row))
    print()

if __name__ == '__main__':
    n = 8
    print(f"Solving {n}-Queens using OR-Tools CP-SAT...")
    solution = solve_n_queens(n)
    print_solution(solution)
