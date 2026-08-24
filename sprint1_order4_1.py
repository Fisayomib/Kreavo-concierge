total = 0
try:
    with open("README.md") as files:
        for line in files:
            if line.startswith("- [ ] "):
                cut = line.strip()[6:]
                total += 1
                print(f"{total}. {cut}")
    if total < 6:
        print(f"Expected total is 6, but {total} tasks were found.")
except FileNotFoundError:
    print("Could not find README.md in this directory")

        
        
