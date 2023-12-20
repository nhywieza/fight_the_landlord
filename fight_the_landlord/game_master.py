import abc
import random
from typing import Literal, Any, Dict, Sequence

from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt
from pydantic import BaseModel, Field, model_validator


def _c2i(x: str) -> int:
    if x == "A":
        return 1
    if x == "2":
        return 2
    if x == "3":
        return 3
    if x == "4":
        return 4
    if x == "5":
        return 5
    if x == "6":
        return 6
    if x == "7":
        return 7
    if x == "8":
        return 8
    if x == "9":
        return 9
    if x == "T":
        return 10
    if x == "J":
        return 11
    if x == "Q":
        return 12
    if x == "K":
        return 13
    raise ValueError("unknown input %s" % x)


def _i2c(x: int) -> str:
    if x == 1:
        return "A"
    if x == 2:
        return "2"
    if x == 3:
        return "3"
    if x == 4:
        return "4"
    if x == 5:
        return "5"
    if x == 6:
        return "6"
    if x == 7:
        return "7"
    if x == 8:
        return "8"
    if x == 9:
        return "9"
    if x == 10:
        return "T"
    if x == 11:
        return "J"
    if x == 12:
        return "Q"
    if x == 13:
        return "K"

    raise ValueError("unknown input %d" % x)


class Card(BaseModel):
    id: int = Field(ge=1, le=54)
    number: int = Field(ge=1, le=15)
    suit: Literal["♠", "♥", "♦", "♣", "Joker", "joker"]

    @model_validator(mode="before")
    @classmethod
    def validate(cls, data: Any) -> Any:
        if data["suit"] == "joker" and data["number"] != 14:
            raise ValueError("joker number must be 14")
        if data["suit"] == "Joker" and data["number"] != 15:
            raise ValueError("joker number must be 15")

        t = {"♠": 1, "♥": 2, "♦": 3, "♣": 4}

        if data["suit"] == "joker":
            data["id"] = 53
        elif data["suit"] == "Joker":
            data["id"] = 54
        else:
            data["id"] = (data["number"] - 1) * 4 + t[data["suit"]]

        return data

    @classmethod
    def from_str(cls, data: str):
        if data == "joker":
            output = {"suit": "joker", "number": 14}
        elif data == "Joker":
            output = {"suit": "Joker", "number": 15}
        elif len(data) != 2:
            raise ValueError("data length error")
        else:
            output = {"suit": data[0], "number": _c2i(data[1])}

        return cls(**output)

    def __str__(self):
        if self.suit == "joker" or self.suit == "Joker":
            return self.suit
        return "%s%s" % (self.suit, _i2c(self.number))


class Deck(BaseModel):
    cards: Dict[int, Card] = {}

    @classmethod
    def from_str(cls, data: str):
        cards_str = data.split(",")
        output = {"cards": {}}
        for card_str in cards_str:
            card = Card.from_str(card_str)
            output["cards"][card.id] = card
        return cls(**output)

    def add(self, card: Card) -> None:
        if card.id in self.cards:
            raise Exception("add card failed, card is %s" % card)
        self.cards[card.id] = card

    def sub(self, card: Card) -> None:
        if card.id not in self.cards:
            raise Exception("sub card failed, card is %s" % card)
        del self.cards[card.id]

    def batch_add(self, cards: Sequence[Card]) -> None:
        for card in cards:
            self.add(card)

    def batch_sub(self, cards: Sequence[Card]) -> None:
        for card in cards:
            self.sub(card)

    def is_empty(self) -> bool:
        return len(self.cards) == 0

    def __str__(self) -> str:
        card_list = list(self.cards.values())

        def _score(x: Card) -> int:
            # 用于排序
            return (x.number + 10) % 13 + 1 if x.number <= 13 else x.number

        card_list.sort(key=lambda u: _score(u), reverse=True)

        return ",".join(map(lambda u: str(u), card_list))


class Player(BaseModel, abc.ABC):
    deck: Deck

    def accept_deck(self, deck: Deck) -> None:
        self.deck = deck

    @abc.abstractmethod
    def call(self) -> bool:
        ...

    @abc.abstractmethod
    def play(self) -> Sequence[Card]:
        ...

    @abc.abstractmethod
    def accept(self, cards: Sequence[Card]) -> None:
        ...

    @abc.abstractmethod
    def reject(self, cards: Sequence[Card]) -> None:
        ...


class ActionFinish(BaseModel):
    ...


class ActionStep(BaseModel):
    check: bool


class Manager(BaseModel):
    state: Literal["NotYetStart", "WaitingToCall", "WaitingToPlay"]
    player_deck: Dict[int, Deck]
    players: Dict[int, Player]
    landlord: int

    def start(self):
        self.distribute_cards()
        self.landlord = self.waiting_to_call()
        self.start_play()

    # def start_play(self):
    #     x = self.landlord
    #
    #     # 出牌
    #     # x 这一轮第一个出牌的 / 目前场上最大的牌
    #     try:
    #         while True:
    #             self.waiting_to_play(x)
    #             # 出完牌看有没有人出牌
    #             while True:
    #                 biggest = True
    #                 for i in range(1, 3):
    #                     y = (x - 1 + i) % 3 + 1
    #                     if self.waiting_to_play(y):
    #                         x = y
    #                         biggest = False
    #                         break
    #                 if biggest:
    #                     break
    #     except Exception:
    #         ...

    @retry(stop=stop_after_attempt(3))
    def waiting_to_play(self, x: int) -> ActionStep | ActionFinish:
        # 等待玩家 X 出牌/校验是否合法/并且保存结果
        # 如果出了牌，那么返回 True，否则为 False
        # 如果牌出完了返回 ActionFinish
        # 每个人只有 3 次出牌机会
        cards = self.players[x].play()
        if len(cards) == 0:
            return ActionStep(check=True)
        self.player_deck[x].batch_sub(cards)
        self.players[x].accept(cards)
        if self.player_deck[x].is_empty():
            return ActionFinish()
        return ActionStep(check=False)

    def distribute_cards(self):
        # 生成手牌
        suits = ['♠', '♥', '♦', '♣']
        numbers = list(map(lambda i: i + 1, range(13)))
        cards = [Card(suit=i, number=j) for i in suits for j in numbers]

        cards.extend(
            [Card(suit="joker", number=14), Card(suit="Joker", number=15)]
        )
        random.shuffle(cards)

        # 发牌
        self.player_deck = {
            0: Deck(cards=cards[-3:]),  # 地主牌
            1: Deck(),
            2: Deck(),
            3: Deck(),
        }
        for i in range(51):
            self.player_deck[i % 3 + 1].add(cards[i])

        for i in range(4):
            self.player_deck[i].sort()

        for i in range(1, 4):
            self.players[i].accept_deck(self.player_deck[i])

    def waiting_to_call(self):
        x = random.randint(1, 3)
        for i in range(3):
            # 等待 x 玩家叫地主
            y = (x - 1 + i) % 3 + 1
            player = self.players[y]
            if player.call():
                return y

        # 没人叫的话给第一家
        return x


class UserProxy(Player):
    def call(self) -> bool:
        return True


class AIAgent(object):
    ...


if __name__ == "__main__":
    load_dotenv()
    card = Card(suit="♠", number=13)
    assert str(card) == "♠K"
    card = Card.from_str("♣A")
    assert str(card) == "♣A"
    assert card.id == 4
    deck = Deck.from_str("♠K,♣A")
    assert str(deck) == "♣A,♠K"
    deck.batch_add([Card.from_str("♣2"), Card.from_str("Joker")])
    assert str(deck) == "Joker,♣2,♣A,♠K"
    deck.batch_add([Card.from_str("♦2")])
    deck.batch_sub([Card.from_str("♣2"), Card.from_str("♦2")])
    assert str(deck) == "Joker,♣A,♠K"
