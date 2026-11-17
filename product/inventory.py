from .store import require, money

class Inventory:
    def __init__(self,store):
        self.store=store

    def stock(self,id,count,cost,price):
        require(count>=0,'库存数量无效')
        return self.store.put('product',id,dict(count=count,cost=money(cost),price=money(price)),create=True)

    def reserve(self,items):
        with self.store.atomic():
            for key,count in items.items():
                record=self.store.get('product',key)
                require(count>0 and record['count']>=count,'组合商品不可售')
                record['count']-=count
                self.store.put('product',key,record)
        return dict(reserved=items)
