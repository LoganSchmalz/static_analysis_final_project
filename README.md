# Motivation

This project implements a toy borrow checker with the following rules:
* A mutable borrow to a container object does not invalidate any references to its first level children.
* A mutable borrow to a container object  invalidates any references to children beyond the first level.
* and to be explicit: A mutable borrow to a higher-level container of a container object invalidates any references to the container

The motivation originates from the following examples:
```
let mut state = State {scores: vec![1,2,3], game_status: true};
let status = &state.game_status;
let s = &mut state;
s.update_scores();
println!("{}", status);
```
Since `update_scores()` does not destroy `s`, the `game_status` field is still accessible from the same location (and is guaranteed to be an accessible field in a `State` struct under static typing).

```
let mut state = State {scores: vec![1,2,3], game_status: true};
let score_team1 = &state.scores[0];
let s = &mut state;
s.update_scores();
println!("{}", score_team1);
```
However in this case, `update_scores()` may for example change the size of the `scores` vec, causing a reallocation of the backing array, causing `score_team1` to no longer reference a valid location.

Also, it should not be possible to pass in the same object multiple times to the same function if it is mutable in one of those instances. E.g. `swap(x,x)` could cause odd behavior; this also applies to `swap(a,b)` if both `a` and `b` could point to `x`.

# Implementation

To mirror these concepts using Python as a base, I have implemented the following features:
* Functions have `references(var)` and `modifies(var)` statements which indicate that a particular parameter is taken as a reference, and may also be modified.
  * A `modifies` variable must also be `references` (which was just done to simplify a little bit of code).
* A reference can be taken by using `ref(var)` so a new variable can be assigned the reference e.g. `x = ref(y)`.
* Objects with attributes are supported e.g. `a.b.c.d = 1` is valid and references to any level of those attributes are properly checked.
* Nested references are automatically cast to single-level references, for simplicity and due to the lack of type-checking. There is no dereferencing operator, also for simplicity.
* This is all done with a potential-points-to analysis that keeps track of the "borrow version" of a variable.
  * e.g. `a.b -> {(x.y.z, v1.2.3), (x.y.w, v1.1.4)}`
* The most up-to-date version of every attribute is kept track of in a separate container
  * e.g. `x: v1, x.y: v3, x.y.z: v2`
  * Then these are checked at access time: e.g. if the most recent version of `x.y.z` that `a.b` might point to is `v1.2.3`, then it will be noted that the version for `x` is the same, the version for `x.y` is out-of-date (invalid), and the version for `x.y.z` would technically be up-to-date if `x.y` was not out of date.
* Practically speaking, there is a lot of time complexity that goes into keeping track of and checking the versions appropriately. My version of this borrow-checking-style analysis is probably substantially less efficient than less-precise real-world implementations.

# Example: if_modify.py
```
                    # all versions are initialized to v0
a.b.c.d = 1         # a.b.c.d: v1
x.y.z = 2           # x.y.z: v1
z = ref(a.b.c.d)    # z -> {a.b.c.d: v0.0.0.1}
if a.b.c.e:         
    z = ref(x.y.z)  # z -> {a.b.c.d: v0.0.0.1, x.y.z: v0.0.1}
y = ref(x)          # y -> {x: v0}
modify(y)           # Before call: Safe because y points to most recent version of x
                    # After call: y -> {x: v1}, x: v1
something(z)        # Not safe, z does not point to the most recent version of x.y.z
                    # if the conditional was taken above
                    # The most recent version of x.y.z is v1.0.1
                    # because x was updated in the modify(y) function call
                    # however z points to v0.0.1
```

# Test Cases

Run the test cases with:
```
python3 prover.py tests/_file_
```

The files demonstrate the following properties:
| File | Property | Valid |
|------|----------|---------|
| basic.py | Test case for `ref(var)` parsing | Yes |
| reject_ref_expr.py | An example where `ref` is called on a non-variable expression | No |
| swap.py | Test case for two variables that may alias to the same object being passed into a function where it might be modified | No |
| struct_fields.py | Basic testing for objects with attributes, including an invalid access at the end | No |
| valid_modify.py | An example where a first-level parent is modified, which leaves its direct child modifiable | Yes |
| nested_invalid_ref.py | A test case where nested references still need their versions checked | No |
| if_modify.py | A test case where a reference may conditionally point to a later modified object | No |
| modify_from_fn.py | A case where a modification to a second-level parent is done by a function instead of by an assignment like in struct_fields.py to demonstrate that functions update the versions of modified arguments | No |
| double_modify.py | A modified variable should automatically have its reference versions updated; demonstrates an edge case where a variable might reference a parent or a second-level child, but either way modifying the reference should consistently be valid since the variable should keep its alias to the correct parent *or* child version after modification (essentially, recursive data structures need to be allowed) | Yes |

# Limitations

This analysis has the following limitations:
* Type-checking is not implemented to save development time. Thus objects do not actually have to be well-defined, functions don't take particular types, variables can be reassigned a with a different type.
  * However, arguments passed into functions for references parameters are required to be instantiated as a reference.
  * In a practical implementation, type-checking definitely prevents some odd programs that can be constructed currently with potentially ambiguous or outright broken semantics.
* Function bodies are not actually checked, since this is a relatively trivial extension by just running the full check process on each function body individually.
* The book-keeping is not sufficient for the hypothetical scenario where a function returns references right now. There are no "lifetimes" or equivalent that would be able to keep track of this.
* Vectors are not implemented, since the syntax is slightly different from object attributes I didn't feel like messing with it, but the rules would remain the same with the following important note: an element in a vector counts as a *second*-level child element to the vector, since the vector would first contain an array and then the array contains the elements (i.e. an access is actually `vec._internal_array[b]`). This would have required some slight adjustments as a result of the syntax `vec[b]` indicating a two-level step rather than a one-level step like `a.b`.
* I didn't implement literal arithmetic expressions since e.g. `a = expr_b + expr_c` is just a slight AST difference to `a = add(expr_b, expr_c)`, and they would follow the same borrowing rules.

# Practical Insights

From this project, I learned that I think Rust's borrow-checking uses Aliasing XOR Mutability as a rule to *substantially* simplify the book-keeping for borrow-checking. Additionally, as I was inspired to try writing these non-standard rules by the [Group Borrowing article](https://verdagon.dev/blog/group-borrowing), I think its algorithm using the notion of groups is also more advanced to improve time complexity and code abstraction.