# procedures: name -> dict with keys: params, requires, ensures, body
_procedures = {}

_alias_map = {}

_base_versions = {}

def get_version(var: tuple):
    return _base_versions.get(var[:len(var)], tuple([0] * (len(var))))

def new_version(var: tuple):
    parent_version = []
    for i in range(1,len(var)):
        next_version = _base_versions.get(var[:i], tuple([0] * i))
        parent_version += (next_version[-1],)

    # parent_version = _base_versions.get(var[:len(var)-1], [0] * (len(var)-1))
    curr_version = _base_versions.get(var[:len(var)], parent_version + [0])
    new_version = tuple(parent_version) + tuple([curr_version[-1] + 1])
    _base_versions[var[:len(var)]] = tuple(new_version)

def validate_version(var: list, curr_version: tuple):
    curr_version = curr_version[:len(var)-2]
    for i in range(len(curr_version)+1):
        parent_version = get_version(var[:i])
        if any(c < p for c, p in zip(curr_version, parent_version)):
            # a child has a version less than parent means it is not up to date and should be invalidated
            return False
    return True

def get_bases(var):
    """
    Resolve and return the set of base paths reachable from 'var' by
    following immediate alias links stored in _alias_map.
    
    This performs a transitive closure (graph reachability) and handles cycles.

    _alias_map[var] = { (target_path, version_tuple), ... }

    We ignore versions during reachability and follow only target_path.
    """
    # Convert plain strings into 1-tuples
    if isinstance(var, str):
        var = (var,)

    frontier = {var}
    seen = set()
    bases = set()

    while frontier:
        v = frontier.pop()
        if v in seen:
            continue
        seen.add(v)

        if v in _alias_map:
            # `_alias_map[v]` contains entries `(path_tuple, version_tuple)`
            for (path, ver) in _alias_map[v]:
                frontier.add(path)
        else:
            # No alias outgoing => v is a base path
            bases.add(v)

    return bases

def extract_ref_target(inner_expr):
    """
    Accepts the expression inside ref(...).
    For standard semantics, only l-values are allowed; currently we support only ["var", name].
    Returns a set containing the immediate target variable name.

    Raises an Exception for non-lvalue expressions.
    """
    match inner_expr:
        case ["var", v]:
            return (v,)
        case ["getattr", ["var", base], *rest]:
            return (base, *rest)
        # Future l-values (arrays, fields) can be added here:
        # case ["index", arr, idx]:
        #     return f"{arr}[{idx}]"  # placeholder representation
        case _:
            raise Exception(
                f"Invalid ref target: {inner_expr}. References must point to variables (l-values)."
            )

def is_array_var(name: str):
    return name and name[0].isupper()


def check(stmt, is_conditional):
    match stmt:
        case ["seq", *rest]:
            for s in rest:
                check(s, is_conditional)

        case ["if", test, body, orelse]:
            check(test, is_conditional)
            check(["seq"] + body, True)
            check(["seq"] + orelse, True)

        case ["skip"]:
            return

        case ["modifies", cond]:
            return

        case ["references", cond]:
            return

        case ["ref", var]:
            # this does nothing, handling will be done in assign
            return

        case ["assign", var, expr]:
            # do something special if rhs is ref(var)
            # otherwise dont worry about it maybe?
            var = (var,)

            match expr:
                case ["ref", inner]:
                    target = extract_ref_target(inner)

                    version = get_version(target)

                    if is_conditional:
                        old = _alias_map.get(var, set())
                        _alias_map[var] = old | {(target, version)}
                    else:
                        _alias_map[var] = {(target, version)}
                    return
                case ["var", rhs]:
                    # kill alias because now refers to a value
                    if var in _alias_map:
                        del _alias_map[var]
                    return
                case _:
                    # arbitrary expression, meaningful computation may occur
                    # kill alias because now refers to a value
                    if var in _alias_map:
                        del _alias_map[var]
                    return

        case ["return", *rest]:
            check(rest, is_conditional)

        case ["store", arr, idx, val]:
            # this should be essentially the same as assign
            return
        
        case ["setattr", ["var", base], *rest, attr, rhs]:
            var = (base, *rest, attr)
            new_version(var)
            print(var, get_version(var))
            return

        case ["proc", name, params, body, references, modifies]:
            # register procedure contracts for later use
            _procedures[name] = {
                "params": params,
                "body": body,
                "references": references,
                "modifies": modifies,
            }

            # TODO: we would need to verify the body as well in a real implementation
            # but for now we will assume functions are nicely defined because this is a trivial extension

        case ["while", cond, body]:
            check(cond, is_conditional)
            check(["seq"] + body, True)

        case ["call", proc, args]:
            procedure = _procedures[proc]
            params = procedure["params"]
            modifies = procedure["modifies"]
            references = procedure["references"]

            # Step 1: reference parameters must receive references (immediate ref)
            for p, a in zip(params, args):
                if p in references:
                    if a[0] != "var":
                        raise Exception(f"In call to {proc}: argument {a} for parameter {p} must be a variable reference")
                    varname = (a[1],)
                    if varname not in _alias_map:
                        raise Exception(
                            f"In call to {proc}: argument {a} for parameter {p} must be a reference"
                        )
                    
                   # --- Version validation for incoming references ---
                    for alias, version in _alias_map[varname]:
                        if not validate_version(alias, version):
                            raise Exception(
                                f"In call to {proc}: argument {a} for parameter {p} "
                                f"is invalid because it refers to a stale version of an object: {alias}"
                            )

 

            # Step 2: resolve each argument to its set of base variables
            param_bases = {}

            print(params)
            print(args)
            for p, a in zip(params, args):
                if a[0] == 'var':
                    param_bases[p] = get_bases(a[1])
                else:
                    param_bases[p] = "N/A"

            # Step 3: check may-alias conflicts
            for i in range(len(params)):
                for j in range(i + 1, len(params)):
                    p1, p2 = params[i], params[j]

                    if p1 not in modifies and p2 not in modifies:
                        # if both are immutable, ignore
                        continue

                    bases1 = param_bases[p1]
                    bases2 = param_bases[p2]
                    print("Bases", bases1, bases2)
                    if bases1 & bases2:  # non-empty intersection => may-alias
                        raise Exception(
                            f"In call to {proc}: illegal aliasing: parameters {p1} and {p2} "
                            f"may refer to overlapping bases {bases1 & bases2} but one or both are modified."
                        )
            return

        case ["const", _] | ["var", _]:
            return

        case ["+", lhs, rhs] | ["-", lhs, rhs] | ["*", lhs, rhs] | ["/", lhs, rhs]:
            return

        case ["or", lhs, rhs] | ["and", lhs, rhs]:
            return

        case (
            ["==", lhs, rhs]
            | ["<", lhs, rhs]
            | ["<=", lhs, rhs]
            | [">", lhs, rhs]
            | [">=", lhs, rhs]
        ):
            return
        
        case ['getattr', ['var', base], *rest]:
            # need to do something here to check if base.rest... is still valid, maybe
            return

        case _:
            raise NotImplementedError(stmt)


def check_expr(
    expr,
):  # not sure if necessary or if i should put it in the regular check call?
    match expr[0]:
        case "const":
            pass
        case "var":
            pass
        case "+":
            pass
        case "-":
            pass
        case "*":
            pass
        case _:
            pass
    return


if __name__ == "__main__":
    from parser import py_ast, WhilePyVisitor
    import sys

    filename = sys.argv[1]
    tree = py_ast(filename)
    visitor = WhilePyVisitor()
    stmt = visitor.visit(tree)
    print("Program AST:", stmt)

    # preprocess functions
    # something like the following just to note them down
    # i = 0
    # while i < len(stmt):
    #     if stmt[i][0] == 'proc':
    #         pre = wp(stmt[i], post)
    #         del stmt[i]
    #     else:
    #         i += 1

    check(stmt, False)
    print(_alias_map)
