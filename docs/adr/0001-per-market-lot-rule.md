# Per-market lot rules in the order guard

The bridge guard used to reject every volume that was not a multiple of 100. That is right for the
main board and ChiNext, but the STAR market starts at 200 shares and the Beijing Stock Exchange at
100, both rising in one-share steps above the minimum. The guard now classifies the stock by its
code prefix and applies that board's minimum and step.

## Consequences

A 100-share STAR-market order is refused locally instead of reaching the broker, where it would be
rejected anyway. The sell-side "remainder below the minimum goes in one order" rule is not enforced
because the guard cannot see the position; it checks the increment only.