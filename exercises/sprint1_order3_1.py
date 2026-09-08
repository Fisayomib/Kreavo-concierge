def calculate_sum(n):
    total = 0
    for i in range(1, n + 1):
        total += i
    return total

calculated_sum = calculate_sum(10)
print("Sum of numbers from 1 to 10:", calculated_sum)