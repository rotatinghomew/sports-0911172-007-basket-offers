from .store import require, money

from .inventory import Inventory

class Baskets:
    def __init__(self,store):
        self.store=store

    def close(self,id,purchase,person,at,items,promotion=None,gifts=None):
        gifts=gifts or []
        require(bool(items) and set(gifts)<=set(items),'商品与赠品无效')
        with self.store.atomic():
            Inventory(self.store).reserve(items)
            net=sum(self.store.get('product',key)['price']*count for key,count in items.items() if key not in gifts)
            unit_cents={key:0 if key in gifts else self.store.get('product',key)['price'] for key in items}
            return self.store.put('basket',id,dict(purchase=purchase,person=person,at=at,
                items=items,gifts=gifts,promotion=promotion,cents=net,returned={},unit_cents=unit_cents),create=True)

    def purchase(self,id):
        return [record for record in self.store.all('basket') if record['purchase']==id]
