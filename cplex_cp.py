"""
N-Queens solver using IBM CPLEX CP Optimizer (docplex.cp).
"""

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
    
    # Solve the model
    # LogVerbosity='Quiet' suppresses verbose output
    result = model.solve(TimeLimit=timeout, LogVerbosity='Quiet')
    
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
