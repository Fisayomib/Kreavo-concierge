name_age = {"Alice": 30, "Bob": 25, "Charlie": 35}
def summ(data):
    tottal = 0
    for i in data.values():
        tottal += i
    return tottal

print(summ(name_age))