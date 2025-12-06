def modify(x):
    references(x)
    modifies(x)
    pass

a.b.c.d = 1
z = ref(a.b)
if x:
    z = ref(a.b.c.d)
modify(z)
modify(z)