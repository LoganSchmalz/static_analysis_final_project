def modify(x):
    references(x)
    modifies(x)
    pass

def something(x):
    references(x)
    pass

a.b.c.d = 1
z = ref(a.b.c.d)
y = ref(a.b)
modify(y)
w = ref(z)
something(w)