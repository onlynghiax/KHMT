from pysat.solvers import Glucose3

def generate_variables(n):
    """Generates a 2D list of variables for the NxN board."""
    return [[i * n + j + 1 for j in range(n)] for i in range(n)]

def at_most_one(clauses, variables, next_var):
    """
    Adds sequential counter encoding clauses for at-most-one constraint.
    Returns the updated next_var.
    """
    n = len(variables)
    if n <= 1:
        return next_var
    if n == 2:
        clauses.append([-variables[0], -variables[1]])
        return next_var

    # Variables: x_0, ..., x_{n-1}
    # Auxiliary variables: r_0, ..., r_{n-2}
    r = [next_var + i for i in range(n - 1)]
    next_var += (n - 1)
    
    # ¬x_0 ∨ r_0
    clauses.append([-variables[0], r[0]])
    
    for i in range(1, n - 1):
        # ¬x_i ∨ r_i
        clauses.append([-variables[i], r[i]])
        # ¬r_{i-1} ∨ r_i
        clauses.append([-r[i-1], r[i]])
        # ¬x_i ∨ ¬r_{i-1}
        clauses.append([-variables[i], -r[i-1]])
        
    # ¬x_{n-1} ∨ ¬r_{n-2}
    clauses.append([-variables[n-1], -r[n-2]])
    
    return next_var

def exactly_one(clauses, variables, next_var):
    """
    Adds clauses for exactly-one constraint (at least one AND at most one).
    Returns the updated next_var.
    """
    clauses.append(list(variables))  # At least one
    return at_most_one(clauses, variables, next_var)

def generate_clauses(n, variables):
    """Generates all constraints for the N-Queens problem."""
    clauses = []
    next_var = n * n + 1
    
    # Row constraints: exactly one queen per row
    for i in range(n):
        next_var = exactly_one(clauses, variables[i], next_var)
        
    # Column constraints: exactly one queen per column
    for j in range(n):
        col = [variables[i][j] for i in range(n)]
        next_var = exactly_one(clauses, col, next_var)
        
    # Diagonal constraints (top-left to bottom-right): at most one queen
    for d in range(-n + 1, n):
        diag = [variables[i][i-d] for i in range(n) if 0 <= i-d < n]
        if len(diag) > 1:
            next_var = at_most_one(clauses, diag, next_var)
            
    # Anti-diagonal constraints (top-right to bottom-left): at most one queen
    for d in range(2 * n - 1):
        diag = [variables[i][d-i] for i in range(n) if 0 <= d-i < n]
        if len(diag) > 1:
            next_var = at_most_one(clauses, diag, next_var)
            
    return clauses

def solve_n_queens(n):
    """
    Solves the N-Queens problem using sequential counter SAT encoding.
    Returns the solution board as a 2D list of 0s and 1s, or None if no solution exists.
    """
    if n <= 0:
        return []
    if n == 1:
        return [[1]]
    
    variables = generate_variables(n)
    clauses = generate_clauses(n, variables)
    
    with Glucose3() as solver:
        for clause in clauses:
            solver.add_clause(clause)
            
        if solver.solve():
            model = solver.get_model()
            board = [[0] * n for _ in range(n)]
            for val in model:
                if val > 0 and val <= n * n:
                    val -= 1
                    r, c = divmod(val, n)
                    board[r][c] = 1
            return board
            
    return None

def print_solution(solution):
    """Prints the board nicely."""
    if solution is None:
        print("No solution exists.")
        return
    for row in solution:
        print(" ".join("Q" if cell else "." for cell in row))

if __name__ == '__main__':
    n = 8
    print(f"Solving {n}-Queens using Sequential Counter SAT Encoding...")
    solution = solve_n_queens(n)
    print_solution(solution)
