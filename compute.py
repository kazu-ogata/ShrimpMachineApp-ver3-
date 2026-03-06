AVG_WEIGHT = 0.00333  # 3.33mg in grams
FEED_RATE = 0.15     # 15% feeding rate

def compute_feed(count):
    biomass = count * AVG_WEIGHT
    feed_per_day = biomass * FEED_RATE
    
    portion = feed_per_day / 5
    
    return biomass, feed_per_day, portion