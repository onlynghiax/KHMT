def solve_n_queens(n, timeout=300):
    """
    Solve the N-Queens problem using Gurobi MIP solver.
    """
    try:
        import gurobipy as gp
        from gurobipy import GRB
    except ImportError:
        print("Error: gurobipy is not installed.")
        return None

    try:
        # Create a new environment with suppressed output
        env = gp.Env(empty=True)
        env.setParam("OutputFlag", 0)
        env.start()
        
        # Create a new model
        model = gp.Model("n_queens", env=env)
        
        # Set timeout parameter
        if timeout is not None:
            model.Params.TimeLimit = timeout
            
        # Create variables: x[i,j] = 1 if a queen is placed at row i, col j
        x = model.addVars(n, n, vtype=GRB.BINARY, name="x")
        
        # Row constraints: Exactly one queen per row
        model.addConstrs((x.sum(i, '*') == 1 for i in range(n)), name="row")
        
        # Column constraints: Exactly one queen per column
        model.addConstrs((x.sum('*', j) == 1 for j in range(n)), name="col")
        
        # Diagonal constraints (i - j = const): At most one queen per diagonal
        model.addConstrs(
            (gp.quicksum(x[i, i-d] for i in range(max(0, d), min(n, n+d))) <= 1 
             for d in range(-n+1, n)), name="diag"
        )
        
        # Anti-diagonal constraints (i + j = const): At most one queen per anti-diagonal
        model.addConstrs(
            (gp.quicksum(x[i, d-i] for i in range(max(0, d-n+1), min(n, d+1))) <= 1 
             for d in range(2*n - 1)), name="anti_diag"
        )
        
        # Optimize model
        model.optimize()
        
        # Extract solution
        solution = None
        if model.Status == GRB.OPTIMAL or (model.Status == GRB.TIME_LIMIT and model.SolCount > 0):
            solution = [[0 for _ in range(n)] for _ in range(n)]
            for i in range(n):
                for j in range(n):
                    if x[i, j].X > 0.5:
                        solution[i][j] = 1
                        
        # Cleanup
        model.dispose()
        env.dispose()
        
        return solution

    except gp.GurobiError as e:
        print(f"Gurobi Error: {e}")
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None

def print_solution(solution):
    """
    Print the N-Queens solution.
    """
    if not solution:
        print("No solution provided.")
        return
        
    n = len(solution)
    for row in solution:
        print(" ".join("Q" if cell else "." for cell in row))
    print()

if __name__ == '__main__':
    n = 8
    print(f"Solving {n}-Queens using Gurobi MIP...")
    sol = solve_n_queens(n)
    
    if sol:
        print(f"Solution for {n}-Queens:")
        print_solution(sol)
    else:
        print(f"Failed to find a solution for {n}-Queens.")
