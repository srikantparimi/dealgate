from decimal import Decimal


def gross_margin(revenue: Decimal, delivery_cost: Decimal) -> Decimal:
    if revenue <= 0:
        raise ValueError("revenue must be positive")
    return (revenue - delivery_cost) / revenue


def min_price(delivery_cost: Decimal, floor: Decimal) -> Decimal:
    if not (0 <= floor < 1):
        raise ValueError("floor must satisfy 0 <= floor < 1")
    return delivery_cost / (Decimal(1) - floor)
