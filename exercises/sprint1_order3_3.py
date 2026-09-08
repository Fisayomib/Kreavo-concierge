total = 0
with open("README.md") as file:
    for line in file:
        total += 1
print("Total number of lines in README.md:", total)