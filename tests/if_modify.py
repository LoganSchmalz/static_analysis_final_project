def modify(x):
    references(x)
    modifies(x)
    pass

def something(x):
    references(x)
    pass

a.b.c.d = 1
x.y.z = 2
z = ref(a.b.c.d)
if a.b.c.e:
    z = ref(x.y.z)
y = ref(x)
modify(y)
something(z)