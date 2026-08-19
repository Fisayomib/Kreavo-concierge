total = 0
with open("README.md") as files:
    for line in files:
        if line.startswith("- [ ] "):
            cut = line.strip()[6:]
            total += 1
            print(f"{total}. {cut}")
        
        
