from .store import require, money

class Aftersales:
    def __init__(self,store):
        self.store=store

    def refund(self,id,basket,product,count,at):
        with self.store.atomic():
            record=self.store.get('basket',basket)
            previous=record['returned'].get(product,0)
            require(0<count<=record['items'].get(product,0)-previous,'退货数量无效')
            item=self.store.get('product',product)
            cents=count*record['unit_cents'][product]
            result=self.store.put('return',id,dict(basket=basket,product=product,count=count,
                cents=cents,at=at),create=True)
            record['returned'][product]=previous+count
            self.store.put('basket',basket,record)
            item['count']+=count
            self.store.put('product',product,item)
            return result

    def exchange(self,id,returned,replacement):
        source=self.store.get('return',returned)
        target=self.store.get('basket',replacement)
        original=self.store.get('basket',source['basket'])
        require(target['person']==original['person'],'换货购买者不同')
        return self.store.put('exchange',id,dict(returned=returned,replacement=replacement),create=True)
