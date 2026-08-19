total = 0
with open("README.md") as file:
    for line in file:
        total += len(line.split())
print("Total number of words in README.md:", total)