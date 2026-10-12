try:
    from docplex.mp.model import Model
except ImportError:
    Model = None

def solve_n_queens(n, timeout=300):
    """
    Solve the N-Queens problem using IBM CPLEX MIP (Mixed Integer Programming).
    Returns a list of lists representing the n x n board, where 1 indicates a queen,
    or None if no solution is found or docplex is not installed.
    """
    if Model is None:
        print("Error: docplex is not installed. Please install docplex to use this solver.")
        return None

    # Create the model
    mdl = Model(name='n_queens')
    
    # Binary variables x[i, j] = 1 if a queen is placed at row i, column j
    x = {(i, j): mdl.binary_var(name=f'x_{i}_{j}') for i in range(n) for j in range(n)}
    
    # Each row has exactly one queen
    for i in range(n):
        mdl.add_constraint(mdl.sum(x[i, j] for j in range(n)) == 1, f'row_{i}')
        
    # Each column has exactly one queen
    for j in range(n):
        mdl.add_constraint(mdl.sum(x[i, j] for i in range(n)) == 1, f'col_{j}')
        
    # Diagonals: i + j = d, where d ranges from 0 to 2n-2
    for d in range(2 * n - 1):
        mdl.add_constraint(mdl.sum(x[i, j] for i in range(n) for j in range(n) if i + j == d) <= 1, f'diag_{d}')
        
    # Anti-diagonals: i - j = d - n + 1, where d ranges from 0 to 2n-2
    for d in range(2 * n - 1):
        val = d - n + 1
        mdl.add_constraint(mdl.sum(x[i, j] for i in range(n) for j in range(n) if i - j == val) <= 1, f'anti_diag_{d}')
        
    # Set time limit
    if timeout is not None:
        mdl.parameters.timelimit = timeout
        
    # Solve the model, suppressing the log output
    solution = mdl.solve(log_output=False)
    
    if solution:
        board = [[0] * n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                # Retrieve variable value, safe-guard against float precision issues
                if solution.get_value(x[i, j]) > 0.5:
                    board[i][j] = 1
        return board
    else:
        return None

def print_solution(solution):
    """
    Print the board in a readable format.
    """
    if solution is None:
        print("No solution found.")
        return
    for row in solution:
        print(' '.join('Q' if cell == 1 else '.' for cell in row))

if __name__ == '__main__':
    n = 8
    print(f"Solving {n}-Queens using CPLEX MIP...")
    sol = solve_n_queens(n)
    if sol:
        print("Solution found:")
        print_solution(sol)
    else:
        print("Failed to find a solution.")
