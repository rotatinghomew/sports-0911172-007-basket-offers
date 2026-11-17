import random
import json
from datetime import date, timedelta

def generate():
    rng = random.Random(117207)
    operations = []

    def add(command, **arguments):
        operations.append([command, arguments])

    def day(offset):
        return (date(2026, 7, 1) + timedelta(days=offset)).isoformat()
    for index in range(12):
        add('inventory.stock', id=f'sku{index}', count=1000, cost=1000 + index * 100, price=3000 + index * 300)
    add('offers.create', id='bundle', items=['sku0', 'sku1'], discount=500, min_margin=1000)
    for index in range(360):
        if index % 9 == 0:
            add('offers.redeem', id=f'b{index}', offer='bundle', person=f'p{index % 90}', at=day(index % 84))
            continue
        products = {f'sku{index % 12}': 1, f'sku{(index + 1 + index % 4) % 12}': 1}
        gifts = [next(iter(products))] if index % 7 == 0 else []
        add('baskets.close', id=f'b{index}', purchase=f'purchase{index // 2}', person=f'p{index // 2 % 90}', at=day(index // 2 % 84), items=products, promotion='gift-day' if gifts else None, gifts=gifts)
        if index % 8 == 0:
            add('aftersales.refund', id=f'r{index}', basket=f'b{index}', product=next(iter(products)), count=1, at=day(index // 2 % 84 + 5))
    return operations

def main():
    import argparse
    parser = argparse.ArgumentParser(description='生成本地合成业务记录，不包含真实个人资料')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    from pathlib import Path
    Path(args.output).write_text(json.dumps(generate(), ensure_ascii=False, indent=2) + '\n')

if __name__=='__main__':
    main()
