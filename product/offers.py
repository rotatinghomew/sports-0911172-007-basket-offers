from .store import require, money

from .inventory import Inventory

class Offers:
    def __init__(self,store):
        self.store=store

    def create(self,id,items,discount,min_margin,exclusive=True):
        require(bool(items) and len(items)==len(set(items)),'组合商品无效')
        products=[self.store.get('product',key) for key in items]
        revenue=sum(item['price'] for item in products)-money(discount)
        require(revenue>=0 and revenue-sum(item['cost'] for item in products)>=min_margin,'组合毛利不足')
        return self.store.put('offer',id,dict(items=items,discount=discount,
            min_margin=min_margin,exclusive=exclusive,state='active'),create=True)

    def redeem(self,id,offer,person,at,other_offer=None):
        with self.store.atomic():
            record=self.store.get('offer',offer)
            require(record['state']=='active','优惠不可用')
            require(not other_offer or not record['exclusive'],'优惠互斥')
            Inventory(self.store).reserve({key:1 for key in record['items']})
            cents=sum(self.store.get('product',key)['price'] for key in record['items'])-record['discount']
            gross=cents+record['discount']
            remaining=cents
            unit_cents={}
            for key in sorted(record['items'])[:-1]:
                amount=cents*self.store.get('product',key)['price']//gross if gross else 0
                unit_cents[key]=amount
                remaining-=amount
            unit_cents[sorted(record['items'])[-1]]=remaining
            self.store.put('basket',id,dict(purchase=id,person=person,at=at,items={key:1 for key in record['items']},
                gifts=[],promotion=offer,cents=cents,returned={},unit_cents=unit_cents),create=True)
            return self.store.put('redemption',id,dict(offer=offer,basket=id,cents=cents),create=True)
