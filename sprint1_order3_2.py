name_age = {"Alice": 30, "Bob": 25, "Charlie": 35}
total = 0
for age in name_age.values():
    total += age
print("Total age of all individuals:", total)

for name, age in name_age.items():
    print(f"{name} is {age} years old.")