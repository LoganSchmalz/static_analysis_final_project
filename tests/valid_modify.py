def modify(x):
    references(x)
    modifies(x)
    pass

a.b.c.d = 1
z = ref(a.b.c.d)
y = ref(a.b.c)
modify(y)
modify(z)
