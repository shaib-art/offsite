import json
from dataclasses import dataclass, asdict
import requests
from typing import List


@dataclass
class Rank:
    rank: int
    appid: int
    concurrent_in_game: int
    peak_in_game: int


@dataclass
class Response:
    last_update: int
    ranks: List[Rank]

    def __post_init__(self):
        ranks = [Rank(**rank) for rank in self.ranks]


@dataclass
class SteamGamesByConcurrentPlayers:
    response: Response

    def __post_init__(self):
        response: Response(**self.response)

    def json(self):
        return json.dumps(asdict(self), indent=3)


def get_top_games():
    steam_api = 'https://api.steampowered.com/ISteamChartsService/GetGamesByConcurrentPlayers/v1/'
    steam_response = requests.get(steam_api)
    if steam_response.status_code != 200:
        print('Couldn\'t get top games.')
        return
    games = SteamGamesByConcurrentPlayers(**steam_response.json())
    print(games)
    with open('TopGames.json', 'w', encoding='utf-8') as games_file:
        games_file.write(games.json())
    with open('TopGames.json', 'r', encoding='utf-8') as games_file:
        print(games_file.read())


if __name__ == '__main__':
    get_top_games()
