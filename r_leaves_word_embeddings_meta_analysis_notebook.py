# -*- coding: utf-8 -*-
"""r/leaves word embeddings meta analysis notebook

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/14Lq9MYgIImR1SejGsnvjr38ZsIYjBNQi
"""

from gensim.models import Word2Vec
from gensim.test.utils import datapath, get_tmpfile
from gensim.models import KeyedVectors
from gensim.scripts.glove2word2vec import glove2word2vec
from operator import itemgetter
from scipy import spatial
import nltk
from nltk.sentiment.vader import SentimentIntensityAnalyzer
nltk.download('averaged_perceptron_tagger')
nltk.download('vader_lexicon')
import inflect
import time
import numpy as np
import statistics
import json
import itertools

from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from datetime import datetime
import statistics

def _calculate_centroid(model, wordlist):
    '''
    Calculate centroid of the wordlist list of words based on the model embedding vectors
    '''
    centr = np.zeros( len(model.wv[wordlist[0]]) )
    for w in wordlist:
        centr += np.array(model.wv[w])
    return centr/len(wordlist)

def _keep_only_model_words(model, words):
    aux = [ word for word in words if word in model.wv.vocab.keys()]
    return aux

def _get_word_freq(model, word):
    if word in model.wv.vocab:
        wm = model.wv.vocab[word]
        return [word, wm.count, wm.index]
    return None

def _get_model_min_max_rank(model):
    minF = 999999
    maxF = -1
    for w in model.wv.vocab:
        wm = model.wv.vocab[w] #wm.count, wm.index
        rank = wm.index
        if(minF>rank):
            minF = rank
        if(maxF<rank):
            maxF = rank
    return [minF, maxF]

sid = SentimentIntensityAnalyzer()
def _get_sentiment(word):
    return sid.polarity_scores(word)['compound']

'''
Normalises a value in the positive space
'''    
def _normalise(val, minF, maxF):
    #print(val, minF, maxF)
    if(maxF<0 or minF<0 or val<0):
        raise Exception('All values should be in the positive space. minf: {}, max: {}, freq: {}'.format(minF, maxF, val))
    if(maxF<= minF):
        raise Exception('Maximum frequency should be bigger than min frequency. minf: {}, max: {}, freq: {}'.format(minF, maxF, freq))
    val -= minF
    val = val/(maxF-minF)
    return val

def _get_cosine_distance(wv1, wv2):
    return spatial.distance.cosine(wv1, wv2)

def _get_min_max(dict_value):
    l = list(dict_value.values())
    return [ min(l), max(l)]

def _find_stdev_threshold_sal(dwords, stdevs):
    '''
    dword is an object like {'word':w, 'bias':bias, 'biasW':biasW, 'freq':freq, 'freqW':freqW, 'sal':val, 'wv':wv, 'sent':sent }
    stdevs : minimum stdevs for which we want to compute the threshold

    returns
    outlier_thr : the threshold correpsonding to stdevs considering salience values from the dwrods object list
    '''
    allsal = []
    for obj in dwords:
        allsal.append(obj['sal'])
    stdev = statistics.stdev(allsal)
    outlier_thr = (stdev*stdevs)+sum(allsal)/len(allsal)
    return outlier_thr

def calculate_biased_words(model, targetset1, targetset2, stdevs, 
                         acceptedPOS = ['JJ', 'JJS', 'JJR','NN', 'NNS', 'NNP', 'NNPS','VB', 'VBG', 'VBD', 'VBN', 'VBP', 'VBZ' ], 
                         words = None, force=False):
    '''
    this function calculates the list of biased words towards targetset1 and taregset2 with salience > than the 
    specified times (minstdev) of standard deviation.

    targetset1 <list of strings> : target set 1
    targetset2 <list of strings> : target set 2
    minstdev int : Minium threhsold for stdev to select biased words
    acceptedPOS <list<str>> : accepted list of POS to consider for the analysis, as defined in NLTK POS tagging lib. 
                              If None, no POS filtering is applied and all words in the vocab are considered
    words list<str> : list of words we want to consider. If None, all words in the vocab are considered
    '''
    if(model is None):
        raise Exception("You need to define a model to estimate biased words.")
    if(targetset1 is None or targetset2 is None):
        raise Exception("Target sets are necessary to estimate biased words.")
    if(stdevs is None):
        raise Exception("You need to define a minimum threshold for standard deviation to select biased words.")
   
    tset1 = _keep_only_model_words(model, targetset1) # remove target set words that do not exist in the model
    tset2 = _keep_only_model_words(model, targetset2) # remove target set words that do not exist in the model

    # We remove words in the target sets, and also their plurals from the set of interesting words to process.
    engine = inflect.engine()
    toremove = targetset1 + targetset2 + [engine.plural(w) for w in targetset1] + [engine.plural(w) for w in targetset2]
    if(words is None):
        words = [w for w in model.wv.vocab.keys() if w not in toremove]

    # Calculate centroids 
    tset1_centroid = _calculate_centroid(model, tset1)
    tset2_centroid = _calculate_centroid(model, tset2)
    [minR, maxR] = _get_model_min_max_rank(model)

    # Get biases for words
    biasWF = {}
    biasWM = {}
    for i, w in enumerate(words):
        p = nltk.pos_tag([w])[0][1]
        if acceptedPOS is not None and p not in acceptedPOS:
            continue
        wv = model.wv[w]
        diff = _get_cosine_distance(tset2_centroid, wv) - _get_cosine_distance(tset1_centroid, wv)
        if(diff>0):
            biasWF[w] = diff
        else:
            biasWM[w] = -1*diff

    # Get min and max bias for both target sets, so we can normalise these values later
    [minbf, maxbf] = _get_min_max(biasWF)
    [minbm, maxbm] = _get_min_max(biasWM)

    # Iterate through all 'selected' words
    biased1 = []
    biased2 = []
    for i, w in enumerate(words):
        # Print('..Processing ', w)
        p = nltk.pos_tag([w])[0][1]
        if acceptedPOS is not None and p not in acceptedPOS:
            continue
        wv = model.wv[w]
        # Sentiment
        sent = _get_sentiment(w)
        # Rank and rank norm
        freq = _get_word_freq(model, w)[1]
        rank = _get_word_freq(model, w)[2]
        rankW = 1-_normalise(rank, minR, maxR) 

        # Normalise bias
        if(w in biasWF):
            bias = biasWF[w]
            biasW = _normalise(bias, minbf, maxbf)
            val = biasW * rankW
            biased1.append({'word':w, 'bias':bias, 'biasW':biasW, 'freq':freq, 'rank':rank, 'rankW':rankW, 'sal':val, 'wv':wv.tolist(), 'sent':sent } ) 
        if(w in biasWM):
            bias = biasWM[w]
            biasW = _normalise(bias, minbm, maxbm)
            val = biasW * rankW
            biased2.append({'word':w, 'bias':bias, 'biasW':biasW, 'freq':freq, 'rank':rank, 'rankW':rankW, 'sal':val, 'wv':wv.tolist(), 'sent':sent } ) 

    # Calculate the salience threshold for both word sets, and select the list of biased words (i.e., which words do we discard?)
    stdevs1_thr = _find_stdev_threshold_sal(biased1, stdevs)
    stdevs2_thr = _find_stdev_threshold_sal(biased2, stdevs)
    # biased1.sort(key=lambda x: x['sal'], reverse=True)
    b1_dict = {}
    for k in biased1:
        if(k['sal']>=stdevs1_thr):
            b1_dict[k['word']] = k
    # biased2.sort(key=lambda x: x['sal'], reverse=True)
    b2_dict = {}
    for k in biased2:
        if(k['sal']>=stdevs2_thr):
            b2_dict[k['word']] = k

    #transform centroid tol list so they become serializable
    tset1_centroid = tset1_centroid.tolist() 
    tset2_centroid = tset2_centroid.tolist()
    return [b1_dict, b2_dict]

modelpath = "leaves_w4_f10_e100_d150.model"
model = Word2Vec.load(modelpath)

import time
starttime = time.time()


progress = ['discussion', 'find', 'understanding', 'useful', 'support', 'group', 'approach', 'subreddit', 'perspective', 'benefit', 'therapy', 'positive', 'improve', 'helpful', 'reflect', 'motivate', 'practice', 'sub', 'focused', 'provide', 'information', 'knowledge', 'encourage', 'meditate', 'focusing', 'mindfulness', 'guidance', 'outlook', 'skill', 'guide', 'headspace', 'technique', 'forum', 'compassion', 'practicing', 'tool', 'insight', 'techniques', 'achieve', 'accountability', 'awareness', 'meditating', 'buddhism', 'channel', 'importance', 'identify', 'beneficial', 'engage', 'explore', 'constructive', 'mindful', 'cultivate', 'resources', 'resource', 'acceptance', 'journaling', 'grounded', 'positivity', 'spirituality', 'mediation', 'gratitude', 'refocus', 'community', 'help', 'exercise', 'success', 'create', 'recovery', 'others', 'address', 'methods', 'learn', 'interests', 'journey', 'seek', 'practical', 'strategies', 'reflection', 'meditation', 'develop', 'discipline', 'value', 'growth', 'ideas', 'focus', 'strategy', 'tips', 'behavioral', 'solutions', 'wisdom', 'philosophy', 'introspection', 'structure', 'kindness', 'implement', 'info', 'discuss', 'utilize', 'strengthen', 'dbt', 'meditations', 'reinforce', 'cbt', 'stoicism', 'build', 'experiences', 'form', 'overcome', 'ways', 'suggestions', 'activities', 'groups', 'research', 'insights', 'website', 'lessons', 'psychology', 'mechanisms', 'alternatives', 'literature', 'sources', 'principles', 'behaviors', 'tools', 'perspectives', 'practices', 'habits', 'areas', 'network', 'subreddits', 'challenges', 'options', 'evidence', 'program', 'advice', 'hobbies', 'strength', 'exercises', 'aspects', 'boundaries', 'books', 'concepts', 'studies', 'programs', 'link', 'beliefs', 'foundation', 'concept', 'method', 'apps', 'outlets', 'communities', 'topics', 'links', 'routines', 'data', 'qualities', 'values', 'material', 'recommendations', 'people', 'meetings', 'points', 'things', 'medications', 'stories', 'posts', 'websites', 'site', 'folks', 'projects', 'goals', 'addictions', 'path', 'results', 'vices', 'diet', 'ones', 'threads', 'articles', 'subs', 'skills', 'circumstances', 'examples', 'efforts', 'parts', 'opinions', 'rules', 'supplements', 'factors', 'videos', 'distractions', 'conditions', 'forms', 'guidelines', 'therapists', 'traits', 'affirmations', 'friendships', 'context', 'reasons', 'quotes', 'stuff', 'words', 'benefits', 'steps', 'foods', 'book', 'professionals', 'struggles', 'successes', 'places', 'answers', 'types', 'individuals', 'forums', 'questions', 'substances', 'outcomes', 'remedies', 'accounts', 'treatments', 'stats', 'journeys', 'items', 'possibilities', 'courses', 'services', 'elements', 'teachings']
exasperation = ['gonna', 'haha', 'coke', 'had', 'yup', 'half', 'yeah', 'bad', 'depressed', 'hell', 'kinda', 'miserable', 'fucked', 'bitch', 'sucked', 'wtf', 'insane', 'ridiculous', 'fuck', 'drunk', 'awful', 'sucks', 'omg', 'ass', 'pathetic', 'nasty', 'tho', 'ha', 'oh', 'terrible', 'yesterday', 'sad', 'resin', 'dead', 'retarded', 'sack', 'everytime', 'stupid', 'lol', 'wicked', 'crazy', 'gross', 'crappy', 'fiend', 'sick', 'crack', 'grumpy', 'bc', 'cuz', 'nope', 'dope', 'yea', 'weird', 'horrible', 'lame', 'disgusting', 'dumb', 'balls', 'dank', 'hella', 'eh', 'didnt', 'crap', 'freaking', 'legit', 'yep', 'nah', 'dirty', 'fucker', 'pissed', 'junkie', 'garbage', 'hangovers', 'hahaha', 'dang', 'dying', 'bastard', 'burnt', 'cus', 'worthless', 'hahah', 'lmao', 'crackhead', 'af', 'bruh', 'carts', 'didn', 'last', 'anyways', 'mad', 'pussy', 'alright', 'meh', 'hated', 'lazy', 'straight', 'ok', 'moody', 'paranoid', 'tired', 'anxious', 'lethargic', 'meth', 'irritable', 'sorta', 'dry', 'hungry', 'cos', 'nuts', 'embarrassing', 'cranky', 'annoying', 'broke', 'scared', 'nauseated', 'bum', 'loser', 'tbh', 'guilty', 'till', 'boy', 'groggy', 'idiot', 'brutal', 'nauseous', 'hungover', 'foggy', 'bummed', 'wet', 'dizzy', 'terrified', 'rn', 'lmfao', 'fine', 'okay', 'high', 'stoned', 'afterwards', 'upset', 'blazed', 'weak', 'embarrassed', 'bored', 'forgetful', 'stressed', 'awkward', 'boring', 'empty', 'angry', 'nervous', 'restless', 'ashamed', 'baked', 'depressing', 'exhausted', 'frustrated', 'irritated', 'disappointed', 'confused', 'bitter', 'cloudy', 'tempted', 'panicked', 'zombie', 'hazy', 'dehydrated', 'fatigued', 'uncomfortable', 'annoyed', 'crying', 'edgy', 'sore', 'agitated', 'skinny', 'unmotivated', 'sluggish', 'hopeless', 'drained', 'sweaty', 'horny', 'bloated', 'odd', 'low', 'hate', 'stuck', 'worse', 'sleepy', 'tempting', 'unhappy', 'unproductive', 'worried', 'overwhelmed', 'frustrating', 'dull', 'jealous', 'suicidal', 'desperate', 'strange', 'rough', 'scary', 'fried', 'antsy', 'trapped', 'apathetic', 'useless', 'relieved', 'fuzzy', 'disgusted', 'pointless', 'unstable', 'unbearable', 'thirsty', 'shaky', 'uneasy', 'normal', 'overwhelming', 'stressful', 'numb', 'intense', 'insecure', 'drowsy', 'isolated', 'jittery', 'unpleasant', 'relaxed', 'impatient', 'exhausting', 'defeated', 'disconnected']
[cycle1, cycle1a] = calculate_biased_words(model, progress, exasperation, 4)
[cycle2, cycle2a] = calculate_biased_words(model, [w for w in cycle1.keys()], [w for w in cycle1a.keys()], 4)
[cycle3, cycle3a] = calculate_biased_words(model, [w for w in cycle2.keys()], [w for w in cycle2a.keys()], 4)
[cycle4, cycle4a] = calculate_biased_words(model, [w for w in cycle3.keys()], [w for w in cycle3a.keys()], 4)
[cycle5, cycle5a] = calculate_biased_words(model, [w for w in cycle4.keys()], [w for w in cycle4a.keys()], 4)
[cycle6, cycle6a] = calculate_biased_words(model, [w for w in cycle5.keys()], [w for w in cycle5a.keys()], 4)
print('-> meta-analysis only took us {} seconds!'.format(time.time()-starttime))

print('My seed words related to progress:')
print(progress)
print()
print('Biased words towards progress')
print( [w for w in cycle1.keys()] )
print()
print('Layer 1 metabiased words towards progress')
print( [w for w in cycle2.keys()])
print()
print('Layer 3 metabiased words towards progress')
print( [w for w in cycle3.keys()])
print()
print('Layer 4 metabiased words towards progress')
print( [w for w in cycle4.keys()])
print()
print('Layer 4 metabiased words towards progress')
print( [w for w in cycle5.keys()])
print()
print('Layer 5 metabiased words towards progress')
print( [w for w in cycle6.keys()])
print()
print()
print('My seed words related to exasperation:')
print(exasperation)
print()
print('Biased words towards exasperation')
print( [w for w in cycle1a.keys()] )
print()
print('Layer 1 metabiased words towards exasperation')
print( [w for w in cycle2a.keys()])
print()
print('Layer 2 metabiased words towards exasperation')
print( [w for w in cycle3a.keys()])
print()
print('Layer 3 metabiased words towards exasperation')
print( [w for w in cycle4a.keys()])
print()
print('Layer 4 metabiased words towards exasperation')
print( [w for w in cycle5a.keys()])
print()
print('Layer 5 metabiased words towards exasperation')
print( [w for w in cycle6a.keys()])

progwordbank = ['discussion', 'find', 'understanding', 'useful', 'support', 'group', 'approach', 'subreddit', 'perspective', 'benefit', 'therapy', 'positive', 'improve', 'helpful', 'reflect', 'motivate', 'practice', 'sub', 'focused', 'provide', 'information', 'knowledge', 'encourage', 'meditate', 'focusing', 'mindfulness', 'guidance', 'outlook', 'skill', 'guide', 'headspace', 'technique', 'forum', 'compassion', 'practicing', 'tool', 'insight', 'techniques', 'achieve', 'accountability', 'awareness', 'meditating', 'buddhism', 'channel', 'importance', 'identify', 'beneficial', 'engage', 'explore', 'constructive', 'mindful', 'cultivate', 'resources', 'resource', 'acceptance', 'journaling', 'grounded', 'positivity', 'spirituality', 'mediation', 'gratitude', 'refocus','community', 'help', 'exercise', 'success', 'create', 'recovery', 'others', 'address', 'methods', 'learn', 'interests', 'journey', 'seek', 'practical', 'strategies', 'reflection', 'meditation', 'develop', 'discipline', 'value', 'growth', 'ideas', 'focus', 'strategy', 'tips', 'behavioral', 'solutions', 'wisdom', 'philosophy', 'introspection', 'structure', 'kindness', 'implement', 'info', 'discuss', 'utilize', 'strengthen', 'dbt', 'meditations', 'reinforce', 'cbt', 'stoicism', 'discussion', 'find', 'understanding', 'support', 'build', 'group', 'approach', 'experiences', 'form', 'perspective', 'overcome', 'therapy', 'ways', 'suggestions', 'activities', 'groups', 'practice', 'provide', 'research', 'insights', 'website', 'information', 'knowledge', 'mindfulness', 'guidance', 'skill', 'lessons', 'guide', 'psychology', 'mechanisms', 'technique', 'compassion', 'alternatives', 'literature', 'tool', 'sources', 'principles', 'insight', 'techniques', 'behaviors', 'awareness', 'buddhism', 'channel', 'importance', 'tools', 'perspectives', 'engage', 'explore', 'cultivate', 'resources', 'resource', 'acceptance', 'spirituality', 'mediation', 'practices','community', 'habits', 'success', 'areas', 'network', 'subreddits', 'create', 'recovery', 'challenges', 'others', 'options', 'evidence', 'program', 'methods', 'advice', 'hobbies', 'strength', 'interests', 'journey', 'exercises', 'seek', 'aspects', 'boundaries', 'books', 'strategies', 'concepts', 'meditation', 'studies', 'develop', 'programs', 'discipline', 'value', 'link', 'growth', 'ideas', 'beliefs', 'strategy', 'tips', 'foundation', 'concept', 'behavioral', 'solutions', 'wisdom', 'method', 'philosophy', 'apps', 'outlets', 'communities', 'topics', 'introspection', 'structure', 'links', 'routines', 'info', 'data', 'qualities', 'utilize', 'dbt', 'meditations', 'values', 'material', 'recommendations', 'cbt', 'stoicism', 'discussion', 'people', 'meetings', 'points', 'things', 'medications', 'support', 'group', 'approach', 'experiences', 'stories', 'form', 'posts', 'websites', 'site', 'perspective', 'folks', 'projects', 'goals', 'addictions', 'path', 'results', 'ways', 'vices', 'suggestions', 'diet', 'activities', 'ones', 'threads', 'groups', 'practice', 'articles', 'subs', 'research', 'skills', 'circumstances', 'insights', 'examples', 'website', 'information', 'knowledge', 'efforts', 'mindfulness', 'guidance', 'skill', 'lessons', 'guide', 'parts', 'opinions', 'rules', 'psychology', 'mechanisms', 'technique', 'supplements', 'alternatives', 'literature', 'tool', 'sources', 'principles', 'insight', 'techniques', 'factors', 'behaviors', 'buddhism', 'channel', 'videos', 'importance', 'tools', 'distractions', 'perspectives', 'conditions', 'forms', 'resources', 'resource', 'guidelines', 'therapists', 'traits', 'practices', 'affirmations', 'community', 'habits', 'areas', 'network', 'subreddits', 'subreddit', 'friendships', 'recovery', 'context', 'challenges', 'others', 'options', 'evidence', 'program', 'reasons', 'quotes', 'methods', 'stuff', 'words', 'benefits', 'advice', 'hobbies', 'steps', 'foods', 'interests', 'journey', 'exercises', 'book', 'aspects', 'boundaries', 'professionals', 'struggles', 'successes', 'books', 'places', 'strategies', 'answers', 'types', 'concepts', 'individuals', 'meditation', 'forums', 'studies', 'programs', 'link', 'ideas', 'questions', 'beliefs', 'strategy', 'tips', 'foundation', 'concept', 'substances', 'solutions', 'wisdom', 'method', 'philosophy', 'apps', 'outlets', 'forum', 'communities', 'topics', 'introspection', 'structure', 'outcomes', 'links', 'routines', 'info', 'remedies', 'data', 'qualities', 'accounts', 'treatments', 'stats', 'meditations', 'values', 'journeys', 'items', 'material', 'possibilities', 'recommendations', 'courses', 'services', 'cbt', 'elements', 'teachings', 'stoicism']
progresswords = []

for i in progwordbank:
  if not i in progresswords:
    progresswords.append(i);
print (progresswords)

fuckwordbank = ['frick', 'frickin', 'freakin', 'freaking,"tweak", "tweaking","fuck', 'fuckin', 'fucking', 'fucky', 'fucked, ’fuckedness', 'motherfucking', 'motherfucker', 'damn', 'goddamn', 'shit', 'shitty', 'shittier', 'shittiest', 'blasted', 'bloody','gonna', 'haha', 'coke', 'had', 'yup', 'half', 'yeah', 'bad', 'depressed', 'hell', 'kinda', 'miserable', 'fucked', 'bitch', 'sucked', 'wtf', 'insane', 'ridiculous', 'fuck', 'drunk', 'awful', 'sucks', 'omg', 'ass', 'pathetic', 'nasty', 'tho', 'ha', 'oh', 'terrible', 'yesterday', 'sad', 'resin', 'dead', 'retarded', 'sack', 'everytime', 'stupid', 'lol', 'wicked', 'crazy', 'gross', 'crappy', 'fiend', 'sick', 'crack', 'grumpy', 'bc', 'cuz', 'nope', 'dope', 'yea', 'weird', 'horrible', 'lame', 'disgusting', 'dumb', 'balls', 'dank', 'hella', 'eh', 'didnt', 'crap', 'freaking', 'legit', 'yep', 'nah', 'dirty', 'fucker', 'pissed', 'junkie', 'garbage', 'hangovers', 'hahaha', 'dang', 'dying', 'bastard', 'burnt', 'cus', 'worthless', 'hahah', 'lmao', 'crackhead', 'af', 'bruh', 'carts','didn', 'last', 'shitty', 'anyways', 'mad', 'pussy', 'shit', 'fucking', 'alright', 'meh', 'hated', 'damn', 'lazy', 'straight', 'ok', 'moody', 'paranoid', 'tired', 'anxious', 'lethargic', 'goddamn', 'meth', 'irritable', 'sorta', 'dry', 'hungry', 'cos', 'nuts', 'embarrassing', 'cranky', 'annoying', 'broke', 'fuckin', 'scared', 'nauseated', 'bum', 'loser', 'tbh', 'guilty', 'till', 'boy', 'groggy', 'idiot', 'brutal', 'nauseous', 'hungover', 'foggy', 'bummed', 'wet', 'dizzy', 'terrified', 'rn', 'lmfao', 'bloody', 'fine', 'yup', 'okay', 'high', 'yeah', 'bad', 'stoned', 'afterwards', 'upset', 'depressed', 'blazed', 'kinda', 'weak', 'embarrassed', 'miserable', 'bored', 'fucked', 'bitch', 'sucked', 'wtf', 'insane', 'forgetful', 'stressed', 'awkward', 'ridiculous', 'drunk', 'awful', 'sucks', 'omg', 'boring', 'pathetic', 'terrible', 'yesterday', 'sad', 'empty', 'dead', 'retarded', 'stupid', 'angry', 'lol', 'nervous', 'crazy', 'gross', 'restless', 'crappy', 'fiend', 'sick', 'ashamed', 'grumpy', 'cuz', 'yea', 'weird', 'horrible', 'lame', 'baked', 'disgusting', 'dumb', 'depressing', 'exhausted', 'frustrated', 'irritated', 'disappointed', 'confused', 'bitter', 'cloudy', 'tempted', 'pissed', 'panicked', 'zombie', 'hazy', 'dehydrated', 'fatigued', 'uncomfortable', 'annoyed', 'crying', 'edgy', 'sore', 'agitated', 'dying', 'skinny', 'unmotivated', 'burnt', 'sluggish', 'hopeless', 'worthless', 'hahah', 'drained', 'lmao', 'sweaty', 'horny', 'bloated', 'af', 'odd', 'low', 'shitty', 'mad', 'pussy', 'fucking', 'hate', 'stuck', 'worse', 'alright', 'meh', 'sleepy', 'hated', 'lazy', 'ok', 'tempting', 'unhappy', 'unproductive', 'nasty', 'worried', 'overwhelmed', 'moody', 'paranoid', 'frustrating', 'tired', 'anxious', 'lethargic', 'dull', 'jealous', 'irritable', 'suicidal', 'dry', 'hungry', 'embarrassing', 'desperate', 'strange', 'cranky', 'annoying', 'fuckin', 'scared', 'nauseated', 'rough', 'bum', 'scary', 'loser', 'guilty', 'fried', 'groggy', 'antsy', 'trapped', 'apathetic', 'useless', 'nauseous', 'hungover', 'foggy', 'relieved', 'bummed', 'fuzzy', 'disgusted', 'pointless', 'unstable', 'unbearable', 'dizzy', 'terrified', 'thirsty', 'shaky', 'fine', 'okay', 'high', 'bad', 'stoned', 'upset', 'depressed', 'uneasy', 'normal', 'weak', 'embarrassed', 'miserable', 'bored', 'fucked', 'sucked', 'insane', 'forgetful', 'stressed', 'awkward', 'ridiculous', 'overwhelming', 'stressful', 'drunk', 'awful', 'sucks', 'boring', 'pathetic', 'terrible', 'sad', 'empty', 'retarded', 'stupid', 'angry', 'nervous', 'crazy', 'gross', 'restless', 'crappy', 'sick', 'numb', 'ashamed', 'grumpy', 'weird', 'horrible', 'lame', 'baked', 'disgusting', 'dumb', 'depressing', 'exhausted', 'frustrated', 'irritated', 'intense', 'disappointed', 'confused', 'bitter', 'insecure', 'cloudy', 'tempted', 'pissed', 'panicked', 'zombie', 'hazy', 'dehydrated', 'fatigued', 'uncomfortable', 'annoyed', 'edgy', 'drowsy', 'agitated', 'isolated', 'dying', 'unmotivated', 'burnt', 'sluggish', 'hopeless', 'worthless', 'drained', 'sweaty', 'horny', 'bloated', 'jittery', 'odd', 'low', 'shitty', 'afterwards', 'mad', 'blazed', 'hate', 'stuck', 'worse', 'alright', 'meh', 'sleepy', 'hated', 'lazy', 'ok', 'tempting', 'unhappy', 'unproductive', 'overwhelmed', 'moody', 'paranoid', 'unpleasant', 'frustrating', 'tired', 'anxious', 'lethargic', 'dull', 'irritable', 'suicidal', 'hungry', 'relaxed', 'embarrassing', 'desperate', 'impatient', 'exhausting', 'strange', 'cranky', 'annoying', 'scared', 'nauseated', 'rough', 'scary', 'guilty', 'fried', 'groggy', 'antsy', 'trapped', 'apathetic', 'useless', 'nauseous', 'hungover', 'foggy', 'defeated', 'sore', 'relieved', 'bummed', 'fuzzy', 'disgusted', 'pointless', 'unstable', 'unbearable', 'dizzy', 'terrified', 'disconnected', 'thirsty', 'shaky', 'gonna', 'haha', 'coke', 'had', 'yup', 'half', 'yeah', 'bad', 'depressed', 'hell', 'kinda', 'miserable', 'fucked', 'bitch', 'sucked', 'wtf', 'insane', 'ridiculous', 'fuck', 'drunk', 'awful', 'sucks', 'omg', 'ass', 'pathetic', 'nasty', 'tho', 'ha', 'oh', 'terrible', 'yesterday', 'sad', 'resin', 'dead', 'retarded', 'sack', 'everytime', 'stupid', 'lol', 'wicked', 'crazy', 'gross', 'crappy', 'fiend', 'sick', 'crack', 'grumpy', 'bc', 'cuz', 'nope', 'dope', 'yea', 'weird', 'horrible', 'lame', 'disgusting', 'dumb', 'balls', 'dank', 'hella', 'eh', 'didnt', 'crap', 'freaking', 'legit', 'yep', 'nah', 'dirty', 'fucker', 'pissed', 'junkie', 'garbage', 'hangovers', 'hahaha', 'dang', 'dying', 'bastard', 'burnt', 'cus', 'worthless', 'hahah', 'lmao', 'crackhead', 'af', 'bruh', 'carts', 'didn', 'last', 'shitty', 'anyways', 'mad', 'pussy', 'shit', 'fucking', 'alright', 'meh', 'hated', 'damn', 'lazy', 'straight', 'ok', 'moody', 'paranoid', 'tired', 'anxious', 'lethargic', 'goddamn', 'meth', 'irritable', 'sorta', 'dry', 'hungry', 'cos', 'nuts', 'embarrassing', 'cranky', 'annoying', 'broke', 'fuckin', 'scared', 'nauseated', 'bum', 'loser', 'tbh', 'guilty', 'till', 'boy', 'groggy', 'idiot', 'brutal', 'nauseous', 'hungover', 'foggy', 'bummed', 'wet', 'dizzy', 'terrified', 'rn', 'lmfao', 'bloody', 'fine', 'yup', 'okay', 'high', 'yeah', 'bad', 'stoned', 'afterwards', 'upset', 'depressed', 'blazed', 'kinda', 'weak', 'embarrassed', 'miserable', 'bored', 'fucked', 'bitch', 'sucked', 'wtf', 'insane', 'forgetful', 'stressed', 'awkward', 'ridiculous', 'drunk', 'awful', 'sucks', 'omg', 'boring', 'pathetic', 'terrible', 'yesterday', 'sad', 'empty', 'dead', 'retarded', 'stupid', 'angry', 'lol', 'nervous', 'crazy', 'gross', 'restless', 'crappy', 'fiend', 'sick', 'ashamed', 'grumpy', 'cuz', 'yea', 'weird', 'horrible', 'lame', 'baked', 'disgusting', 'dumb', 'depressing', 'exhausted', 'frustrated', 'irritated', 'disappointed', 'confused', 'bitter', 'cloudy', 'tempted', 'pissed', 'panicked', 'zombie', 'hazy', 'dehydrated', 'fatigued', 'uncomfortable', 'annoyed', 'crying', 'edgy', 'sore', 'agitated', 'dying', 'skinny', 'unmotivated', 'burnt', 'sluggish', 'hopeless', 'worthless', 'hahah', 'drained', 'lmao', 'sweaty', 'horny', 'bloated', 'af', 'odd', 'low', 'shitty', 'mad', 'pussy', 'fucking', 'hate', 'stuck', 'worse', 'alright', 'meh', 'sleepy', 'hated', 'lazy', 'ok', 'tempting', 'unhappy', 'unproductive', 'nasty', 'worried', 'overwhelmed', 'moody', 'paranoid', 'frustrating', 'tired', 'anxious', 'lethargic', 'dull', 'jealous', 'irritable', 'suicidal', 'dry', 'hungry', 'embarrassing', 'desperate', 'strange', 'cranky', 'annoying', 'fuckin', 'scared', 'nauseated', 'rough', 'bum', 'scary', 'loser', 'guilty', 'fried', 'groggy', 'antsy', 'trapped', 'apathetic', 'useless', 'nauseous', 'hungover', 'foggy', 'relieved', 'bummed', 'fuzzy', 'disgusted', 'pointless', 'unstable', 'unbearable', 'dizzy', 'terrified', 'thirsty', 'shaky', 'fine', 'okay', 'high', 'bad', 'stoned', 'upset', 'depressed', 'uneasy', 'normal', 'weak', 'embarrassed', 'miserable', 'bored', 'fucked', 'sucked', 'insane', 'forgetful', 'stressed', 'awkward', 'ridiculous', 'overwhelming', 'stressful', 'drunk', 'awful', 'sucks', 'boring', 'pathetic', 'terrible', 'sad', 'empty', 'retarded', 'stupid', 'angry', 'nervous', 'crazy', 'gross', 'restless', 'crappy', 'sick', 'numb', 'ashamed', 'grumpy', 'weird', 'horrible', 'lame', 'baked', 'disgusting', 'dumb', 'depressing', 'exhausted', 'frustrated', 'irritated', 'intense', 'disappointed', 'confused', 'bitter', 'insecure', 'cloudy', 'tempted', 'pissed', 'panicked', 'zombie', 'hazy', 'dehydrated', 'fatigued', 'uncomfortable', 'annoyed', 'edgy', 'drowsy', 'agitated', 'isolated', 'dying', 'unmotivated', 'burnt', 'sluggish', 'hopeless', 'worthless', 'drained', 'sweaty', 'horny', 'bloated', 'jittery', 'odd', 'low', 'shitty', 'afterwards', 'mad', 'blazed', 'hate', 'stuck', 'worse', 'alright', 'meh', 'sleepy', 'hated', 'lazy', 'ok', 'tempting', 'unhappy', 'unproductive', 'overwhelmed', 'moody', 'paranoid', 'unpleasant', 'frustrating', 'tired', 'anxious', 'lethargic', 'dull', 'irritable', 'suicidal', 'hungry', 'relaxed', 'embarrassing', 'desperate', 'impatient', 'exhausting', 'strange', 'cranky', 'annoying', 'scared', 'nauseated', 'rough', 'scary', 'guilty', 'fried', 'groggy', 'antsy', 'trapped', 'apathetic', 'useless', 'nauseous', 'hungover', 'foggy', 'defeated', 'sore', 'relieved', 'bummed', 'fuzzy', 'disgusted', 'pointless', 'unstable', 'unbearable', 'dizzy', 'terrified', 'disconnected', 'thirsty', 'shaky']
fuckwords = []
for i in fuckwordbank:
  if not i in fuckwords:
    fuckwords.append(i);
print (fuckwords)

