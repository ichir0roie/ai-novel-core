
from db.schema import *


delete_tables = [
    Event,
    EventCharacter,
    Character,
    CharacterLocation,
    CharacterRelation,
]


def reset_world():

    with get_env_session() as s:
        for t in delete_tables:
            s.execute(delete(t))
        s.commit()


if __name__ == "__main__":
    reset_world()
