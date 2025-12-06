def modify(x):
    references(x)
    modifies(x)
    pass

a.b.c.d = 1
a.b.c.d = 2
z = ref(a.b.c.d)
y = ref(a.b)
modify(y)
# z = ref(a.b.c.d)
modify(z)