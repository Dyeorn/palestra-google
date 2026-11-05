"""Catálogo mock da PetFeliz (pet shop fictício). 40 produtos."""
from __future__ import annotations

import hashlib

from plugin.classifiers import norm

# (nome, categoria, espécie, preço, tags)
_RAW = [
    ("Ração Golden Cães Adultos 10kg", "ração", "cachorro", 159.90, "adulto frango carne"),
    ("Ração Premier Cães Adultos 15kg", "ração", "cachorro", 229.90, "adulto premium"),
    ("Ração Quatree Cães Adultos 10kg", "ração", "cachorro", 109.90, "adulto economica barata"),
    ("Ração Golden Filhotes 10kg", "ração", "cachorro", 169.90, "filhote cachorrinho"),
    ("Ração Royal Canin Mini Filhotes 3kg", "ração", "cachorro", 119.90, "filhote cachorrinho pequeno premium"),
    ("Ração Premier Gatos Castrados 7,5kg", "ração", "gato", 219.90, "castrado adulto premium"),
    ("Ração Whiskas Gatos Adultos 10kg", "ração", "gato", 139.90, "adulto economica"),
    ("Ração Golden Gatos Castrados 10kg", "ração", "gato", 189.90, "castrado adulto frango"),
    ("Ração Royal Canin Gatos Filhotes 2kg", "ração", "gato", 99.90, "filhote gatinho premium"),
    ("Petisco Bifinho Cães 500g", "petisco", "cachorro", 24.90, "bifinho snack adestramento"),
    ("Petisco Ossinho Cães 3 unidades", "petisco", "cachorro", 17.90, "osso snack mastigar"),
    ("Petisco Dental Stick Cães 7 unidades", "petisco", "cachorro", 32.90, "dental higiene snack"),
    ("Petisco Sachê Gatos 12 unidades", "petisco", "gato", 29.90, "sache snack umido"),
    ("Petisco Catnip Gatos 50g", "petisco", "gato", 14.90, "catnip erva snack"),
    ("Bolinha de Borracha Cães", "brinquedo", "cachorro", 19.90, "bola borracha morder"),
    ("Corda Mordedor Cães", "brinquedo", "cachorro", 24.90, "corda mordedor morder"),
    ("Pelúcia Squeeze Cães", "brinquedo", "cachorro", 34.90, "pelucia apito morder"),
    ("Frisbee Resistente Cães", "brinquedo", "cachorro", 39.90, "frisbee disco passeio"),
    ("Varinha com Penas Gatos", "brinquedo", "gato", 22.90, "varinha pena penas pescaria"),
    ("Ratinho de Pelúcia Gatos", "brinquedo", "gato", 12.90, "rato ratinho pelucia"),
    ("Túnel Dobrável Gatos", "brinquedo", "gato", 59.90, "tunel esconderijo"),
    ("Bolinhas com Guizo Gatos 6 unidades", "brinquedo", "gato", 18.90, "bola guizo bolinhas"),
    ("Areia Higiênica Sílica Gatos 3,8kg", "higiene", "gato", 39.90, "areia sanitaria silica caixa"),
    ("Areia Higiênica Granulada Gatos 4kg", "higiene", "gato", 21.90, "areia sanitaria granulada caixa economica"),
    ("Tapete Higiênico Cães 30 unidades", "higiene", "cachorro", 69.90, "tapete xixi filhote"),
    ("Shampoo Neutro Cães 500ml", "higiene", "cachorro", 27.90, "shampoo banho neutro pelo"),
    ("Shampoo Antipulgas Cães 500ml", "higiene", "cachorro", 34.90, "shampoo banho antipulgas pulgas"),
    ("Antipulgas Comprimido Cães Médios", "saúde", "cachorro", 89.90, "antipulgas pulgas carrapato comprimido"),
    ("Antipulgas Pipeta Gatos", "saúde", "gato", 59.90, "antipulgas pulgas pipeta"),
    ("Escova Removedora de Pelos", "higiene", "ambos", 29.90, "escova pelo pelos"),
    ("Cama Redonda Pelúcia Cães M", "cama", "cachorro", 119.90, "cama caminha dormir conforto"),
    ("Cama Iglu Gatos", "cama", "gato", 89.90, "cama caminha iglu dormir"),
    ("Colchonete Impermeável Cães G", "cama", "cachorro", 149.90, "colchonete cama impermeavel grande"),
    ("Coleira Nylon Cães M", "acessório", "cachorro", 29.90, "coleira passeio"),
    ("Peitoral Ajustável Cães M", "acessório", "cachorro", 54.90, "peitoral coleira passeio"),
    ("Guia Retrátil 5m Cães", "acessório", "cachorro", 49.90, "guia passeio retratil"),
    ("Comedouro Inox Antiderrapante", "acessório", "ambos", 34.90, "comedouro pote tigela inox"),
    ("Bebedouro Fonte Gatos 2L", "acessório", "gato", 129.90, "bebedouro fonte agua"),
    ("Arranhador Torre Gatos 80cm", "acessório", "gato", 179.90, "arranhador torre unha"),
    ("Caixa de Transporte M", "acessório", "ambos", 139.90, "caixa transporte viagem"),
    ("Roupinha Moletom Cães P", "acessório", "cachorro", 44.90, "roupa roupinha moletom frio"),
]

PRODUCTS: list[dict] = []
for i, (nome, cat, esp, preco, tags) in enumerate(_RAW, start=1):
    synonyms = {"cachorro": "cachorro cao caes dog", "gato": "gato gatos felino cat", "ambos": "cachorro gato"}[esp]
    PRODUCTS.append({"id": f"P{i:03d}", "nome": nome, "categoria": cat, "especie": esp,
                     "preco": preco, "_texto": norm(f"{nome} {cat} {synonyms} {tags}")})
BY_ID = {p["id"]: p for p in PRODUCTS}

CUPONS = {"PRIMEIRA10": 10, "PET15": 15, "VOLTA20": 20, "FRETE5": 5}
FRETE_FIXO = 14.90
FRETE_GRATIS_ACIMA = 150.0

_STOP = {"para", "pra", "de", "do", "da", "o", "a", "os", "as", "um", "uma", "e", "com", "meu",
         "minha", "no", "na", "quero", "preciso", "procuro", "oi", "ola", "bom", "dia", "tarde",
         "noite", "algum", "alguma", "tem", "ai", "voces", "vcs", "que", "gostaria", "comprar",
         "buscando", "busco", "ver", "por", "favor", "mais", "meus", "sobre", "me", "ajuda"}


def stock_of(pid: str) -> int:
    """Estoque determinístico por produto (~12% dos itens zerados)."""
    n = int(hashlib.md5(pid.encode()).hexdigest()[:4], 16) % 100
    return 0 if n < 12 else n % 30 + 3


def prazo_dias(pid: str) -> int:
    return int(hashlib.md5(("p" + pid).encode()).hexdigest()[:4], 16) % 6 + 1


def _match(tok: str, words: set[str]) -> bool:
    if len(tok) < 4:
        return tok in words
    return any(w.startswith(tok) or (len(w) >= 4 and tok.startswith(w)) for w in words)


def search(consulta: str, limit: int = 4) -> list[dict]:
    toks = [t for t in norm(consulta).replace(",", " ").replace("?", " ").replace("!", " ").replace(".", " ").split()
            if t not in _STOP and len(t) > 2]
    scored = []
    for p in PRODUCTS:
        words = set(p["_texto"].split())
        score = sum(1 for t in toks if _match(t, words))
        if score:
            scored.append((-score, p["preco"], p["id"], p))
    scored.sort(key=lambda x: x[:3])
    return [x[3] for x in scored[:limit]]


def public(p: dict) -> dict:
    return {"id": p["id"], "nome": p["nome"], "categoria": p["categoria"],
            "especie": p["especie"], "preco": p["preco"]}
