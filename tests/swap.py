def swap(x,y):
    references(x)
    references(y)
    modifies(x)
    modifies(y)
    pass

a = 5
b = 6
y = ref(a)
z = ref(b)
swap(y,z)
z = ref(y)
swap(y,z)