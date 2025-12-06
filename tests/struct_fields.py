def modify(x):
    references(x)
    modifies(x)
    pass

a.b.c.d = 1
a.b.c.d = 2
z = ref(a.b.c.d)
a.b = 3
a.b.c.d = 4
y = ref(a.b.c.d)
modify(y)
w = ref(z)
modify(w)