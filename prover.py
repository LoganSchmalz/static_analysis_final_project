# procedures: name -> dict with keys: params, requires, ensures, body
_procedures = {}

_alias_map = {}

_base_versions = {}

def get_full_version(var: tuple):
    version = []
    for i in range(len(var)):
        parent_version = _base_versions.get(var[:i+1], 0)
        version.append(parent_version)
    return tuple(version)            

def new_version(var: tuple):
    curr_version = _base_versions.get(var[:len(var)], 0)
    new_version = curr_version + 1 
    _base_versions[var[:len(var)]] = new_version

def validate_version(var: list, curr_version: tuple):
    curr_version = curr_version[:len(var)-2]
    for i in range(len(curr_version)):
        parent_version = _base_versions.get(var[:i+1], 0)
        if curr_version[i] < parent_version:
            # a child has a version less than parent means it is not up to date and should be invalidated
            return False
    return True

def get_bases_versions(var):
    """
    Resolve and return the set of base paths reachable from 'var' by
    following immediate alias links stored in _alias_map.
    
    This performs a transitive closure (graph reachability) and handles cycles.
    """
    # Convert plain strings into 1-tuples
    if isinstance(var, str):
        var = (var,)

    frontier = {(var,0)}
    seen = set()
    bases = set()

    while frontier:
        v, ver = frontier.pop()
        if v in seen:
            continue
        seen.add(v)

        if v in _alias_map:
            for alias in _alias_map[v]:
                frontier.add(alias)
        else:
            # No alias outgoing => v is a base path
            bases.add((v,ver))

    return bases

def get_bases(var):
    bases_versions = get_bases_versions(var)
    return set(b for b,v in bases_versions)

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

                    version = get_full_version(target)

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
            print(var, get_full_version(var))
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
                    for alias, version in get_bases_versions(varname):
                        if not validate_version(alias, version):
                            raise Exception(
                                f"In call to {proc}: argument {a} for parameter {p} "
                                f"is invalid because it may refer to a stale version of an object: {alias}"
                            )

            # Step 2: resolve each argument to its set of base variables
            param_bases = {}

            for p, a in zip(params, args):
                if a[0] == 'var':
                    param_bases[p] = get_bases(a[1])
                else:
                    param_bases[p] = "N/A"

            # Step 3: check may-alias conflicts
            for i in range(len(params)):
                p1 = params[i]
                bases1 = param_bases[p1]

                for j in range(i + 1, len(params)):
                    p1, p2 = params[i], params[j]

                    if p1 not in modifies and p2 not in modifies:
                        # if both are immutable, ignore
                        continue

                    bases2 = param_bases[p2]
                    if bases1 & bases2:  # non-empty intersection => may-alias
                        raise Exception(
                            f"In call to {proc}: illegal aliasing: parameters {p1} and {p2} "
                            f"may refer to overlapping bases {bases1 & bases2} but one or both are modified."
                        )

                # update versions for any modified references
                if p1 in modifies:
                    assert(args[i][0] == "var")
                    varname = args[i][1]
                    new_versions = set()
                    # order variable tuples so any parents come before children
                    bases = list(bases1)
                    bases.sort(key=lambda x: len(x))
                    for b in bases:
                        new_version(b)
                        new_versions.add((b, get_full_version(b)))
                    _alias_map[(varname,)] = new_versions
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
