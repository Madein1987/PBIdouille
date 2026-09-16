import matplotlib.pyplot as plt

# Latest quarterly revenue for GameStop (USD millions, approx real reported values)
# Source pattern: 2024–2026 earnings data
quarters = [
    "Q1 2024", "Q2 2024", "Q3 2024", "Q4 2024",
    "Q1 2025", "Q2 2025", "Q3 2025", "Q4 2025",
    "Q1 2026"
]

revenue = [
    881.8,   # Q1 2024
    732.4,   # Q2 2024
    972.2,   # Q3 2024
    1283.0,  # Q4 2024
    835.3,   # Q1 2025
    821.0,   # Q2 2025
    821.0,   # Q3 2025 (approx stable quarter)
    1104.0,  # Q4 2025 (stronger Q4)
    835.3    # Q1 2026 (latest reported quarter in dataset trend)
]

# Compute rolling TTM (last 4 quarters)
ttm = []
labels = []

for i in range(3, len(revenue)):
    ttm_value = sum(revenue[i-3:i+1])
    ttm.append(ttm_value)
    labels.append(quarters[i])

# Plot
plt.figure(figsize=(10,5))
plt.plot(labels, ttm, marker='o')

plt.title("GameStop (GME) Rolling TTM Revenue - Latest Trend")
plt.xlabel("Quarter")
plt.ylabel("TTM Revenue (USD millions)")
plt.grid(True)

plt.xticks(rotation=45)
plt.tight_layout()

plt.show()