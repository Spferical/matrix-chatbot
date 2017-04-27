from sqlalchemy import Column, Integer, String, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
import random


Base = declarative_base()


class MarkovEntry(Base):
    __tablename__ = 'markov'
    id = Column(Integer, primary_key=True)
    word1 = Column(String(255))
    word2 = Column(String(255))
    follower = Column(String(255))
    count = Column(Integer, nullable=False)
    word_pair = Index("word_pair", "word1", "word2")


class MarkovDatabaseBrain(object):
    """Stores all data for the chatbot's markov chain in a sqlite database."""
    def __init__(self, database_path):
        engine = create_engine('sqlite:///' + database_path)
        # create any missing tables
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        self.session = Session()

    def add(self, word_pair, follower, count=1, check_existing=True):
        word1, word2 = word_pair
        entry = check_existing and self.session.query(MarkovEntry) \
            .filter_by(word1=word1, word2=word2, follower=follower) \
            .one_or_none()
        if entry:
            entry.count += count
        else:
            new_entry = MarkovEntry(
                word1=word1, word2=word2, follower=follower, count=count)
            self.session.add(new_entry)

    def get_followers(self, word_pair):
        word1, word2 = word_pair
        entries = self.session.query(MarkovEntry) \
            .filter_by(word1=word1, word2=word2)
        return {entry.follower: entry.count for entry in entries}

    def contains_pair(self, word_pair):
        word1, word2 = word_pair
        return bool(self.session.query(MarkovEntry)
                    .filter_by(word1=word1, word2=word2)
                    .first())

    def get_pairs_containing_word_ignoring_case(self, word):
        word = word.lower()
        entries = self.session.query(MarkovEntry)\
            .filter((func.lower(MarkovEntry.word1) == word) |
                    (func.lower(MarkovEntry.word2) == word))\
            .distinct(MarkovEntry.word_pair)
        return ((entry.word1, entry.word2) for entry in entries)

    def get_three_random_words(self):
        assert not self.is_empty()

        query = self.session.query(MarkovEntry)
        count = int(query.count())
        entry = query.offset(int(count * random.random())).first()
        return (entry.word1, entry.word2, entry.follower)

    def is_empty(self):
        query = self.session.query(MarkovEntry)
        return query.first() is None

    def save(self):
        self.session.commit()
