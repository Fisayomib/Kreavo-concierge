total = 0
with open("README.md") as files:
    for line in files:
        if line.startswith("- [ ] "):
            print(line.strip())
        
        
