# I/O Specification

## Input Format: Basket-Transaction File

Tab-separated values, one basket per line:
```
<transaction_id>\t<basket_id>\t<item1> <item2> ...
```

Example (sample_basket.txt):
```
0	0	A B C
0	1	B D
1	2	A C
```

## Output Format: Patterns CSV

```
itemset,start,end,support
A B,3,7,5
B C D,10,15,8
```

- `itemset`: space-separated sorted items
- `start`, `end`: window start range [start, end+W] is the dense period
- `support`: occurrence count within window

## Adapter Contract

All baselines must implement the adapter interface in baselines/adapters/:
- Input: basket-transaction file in above format
- Output: patterns CSV in above format
