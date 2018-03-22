import time

API_BASE_URL = "https://api.douban.com/v2/movie/"
DOUBAN_MOVIE_SEARCH = API_BASE_URL + 'search?q=%s'
DOUBAN_MOVIE_SUBJECT = API_BASE_URL + 'subject/%s'
DOUBAN_MOVIE_IMDB_QUERY = API_BASE_URL + 'imdb/%s'
REQUEST_RETRY_LIMIT = 3

RE_IMDB_ID = Regex('^tt\d+$')
RE_DOUBAN_ID = Regex('\d+$')


def Start():
    HTTP.CacheTime = CACHE_1WEEK


class DBMAgent(Agent.Movies):
    name = 'Douban Movie Database'
    languages = [Locale.Language.English, Locale.Language.Chinese]

    primary_provider = True
    accepts_from = ['com.plexapp.agents.localmedia']
    contributes_to = ['com.plexapp.agents.imdb']

    def search(self, results, media, lang, manual):

        # If search is initiated by a different, primary metadata agent.
        # This requires the other agent to use the IMDb id as key.
        if media.primary_metadata is not None and RE_IMDB_ID.search(media.primary_metadata.id):
            results.Append(MetadataSearchResult(
                id = media.primary_metadata.id,
                score = 100
            ))
            return

        # manual search and name is IMDB id
        if manual and RE_IMDB_ID.search(media.name):
            search_url = DOUBAN_MOVIE_IMDB_QUERY % media.name

            dbm_dict = self.get_json(url=search_url)
            if dbm_dict:
                results.Append(MetadataSearchResult(
                    id = media.name,
                    name = dbm_dict['title'],
                    year = dbm_dict['year'][0],
                    lang = lang
                    ))
            return

        # automatic search
        search_url = DOUBAN_MOVIE_SEARCH % String.Quote(media.name)
        dbm_dict = self.get_json(url=search_url)
        if dbm_dict and 'subjects' in dbm_dict:

            for i, movie in enumerate(dbm_dict['subjects']):

                # if it's episode, then continue
                if movie['subtype'] != 'movie':
                    continue

                score = 90

                dist = abs(String.LevenshteinDistance(
                                movie['title'].lower(),
                                media.name.lower())
                            )

                if movie['original_title'] != movie['title']:
                    dist = min(abs(String.LevenshteinDistance(
                                        movie['original_title'].lower(),
                                        media.name.lower())),
                                dist)

                score = score - dist

                # Adjust score slightly for 'popularity' (helpful for similar or identical titles when no media.year is present)
                score = score - (5 * i)

                release_year = None
                if 'year' in movie and movie['year'] != '':
                    try:
                        release_year = int(movie['year'])
                    except:
                        pass

                if media.year and int(media.year) > 1900 and release_year:
                    year_diff = abs(int(media.year) - release_year)
                    if year_diff <= 1:
                        score = score + 10
                    else:
                        score = score - (5 * year_diff)

                if score < 0:
                    score = 0

                results.Append(MetadataSearchResult(
                    id = movie['id'],
                    name = movie['title'],
                    year = release_year,
                    score = score,
                    lang = lang
                ))


    def update(self, metadata, media, lang):

        proxy = Proxy.Preview

        if RE_IMDB_ID.search(metadata.id):
            url=DOUBAN_MOVIE_IMDB_QUERY % metadata.id
        elif RE_DOUBAN_ID.search(metadata.id):
            url=DOUBAN_MOVIE_SUBJECT % metadata.id
        else:
            Log('Cannot find douban id or imdb id')
            return
        dbm_dict = self.get_json(url)
        if not dbm_dict:
            Log('Failed to get data')
            return

        # Rating
        votes = dbm_dict['ratings_count']
        rating =  dbm_dict['rating']['average']
        if votes > 3:
            metadata.rating = float(rating)

        # Year
        if dbm_dict['year']:
            metadata.year = int(dbm_dict['year'])

        # Title of the film
        metadata.title = dbm_dict['title']

        if metadata.title != dbm_dict['original_title']:
            metadata.original_title = dbm_dict['original_title']

        # Summary
        if dbm_dict['summary']:
            metadata.summary = dbm_dict['summary']

        # Genres
        metadata.genres.clear()
        for genre in dbm_dict['genres']:
            metadata.genres.add(genre.strip())

        # Countries
        metadata.countries.clear()
        for country in dbm_dict['countries']:
            metadata.countries.add(country.strip())

        # Directors
        metadata.directors.clear()
        for director in dbm_dict['directors']:
            d = metadata.directors.new()
            d.name = director['name']
            if director['avatars']:
                d.photo = director['avatars']['large']

        # Casts
        metadata.roles.clear()
        for cast in dbm_dict['casts']:
            role = metadata.roles.new()
            role.name = cast['name']
            if cast['avatars']:
                role.photo = cast['avatars']['large']

        # Posters
        if len(metadata.posters.keys()) == 0:
            poster_url = dbm_dict['images']['large']
            thumb_url = dbm_dict['images']['small']
            metadata.posters[poster_url] = proxy(HTTP.Request(thumb_url), sort_order=1)


    def get_json(self, url, cache_time=CACHE_1HOUR * 3):
        # try n times waiting 5 seconds in between if something goes wrong
        result = None
        for t in reversed(range(REQUEST_RETRY_LIMIT)):
            try:
                result = JSON.ObjectFromURL(url, sleep=2.0, cacheTime=cache_time)
            except:
                Log('Error fetching JSON from The Movie Database, will try %s more time(s) before giving up.', str(t))
                time.sleep(5)
                continue

            if isinstance(result, dict):
                return result

        Log('Error fetching JSON from Douban.')
        return None
