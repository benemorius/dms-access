
# Stuff for connecting to AD
ad_string = '(objectClass=person)'
ad_address = '127.0.0.1'
ad_user = 'user'
ad_password = 'password'

# Hardcoded pin number for testing
hard_pins = [
    #'1234',
    #'567890',
    #'EYui9um4',
]

# Layout of doors, incoming number and outgoing relay
door_layout = {
    # '11':'1', # front door
    # '12':'4', # back door
    # '13':'2', # workshop
    # '14':'3', # woodshop
    # '15':'5', # server
    # '16':'6', # electrical
    # '17':'7', # garage
}

# Doors accessible by all badges
common_doors = [
    # '11',
    # '12',
    # '13',
    # '14',
]

# Doors accessible by server badges
server_doors = [
    # '15',
]

# Doors accessible by electrical badges
electrical_doors = [
    # '16',
]

# Doors accessible by garage badges
garage_doors = [
    # '17',
]

# Hardcoded badges with common access
common_badges = [
    # '7777777',
]

# Badges with server room access
server_badges = [
    # '7777777',
]

# Badges with electrical room access
electrical_badges = [
    # '7777777',
]

# Badges with garage door access
garage_badges = [
    # '7777777',
]

# Badges which are denied access no matter what
# (meaning they may work in the old system, but they will not work in this one)
blacklisted_badges = [
    # '6666666',
]

try:
    import config_local as l
except (ImportError):
    pass
else:
    hard_pins.extend(l.hard_pins)
    door_layout.update(l.door_layout)
    common_doors.extend(l.common_doors)
    server_doors.extend(l.server_doors)
    electrical_doors.extend(l.electrical_doors)
    garage_doors.extend(l.garage_doors)
    common_badges.extend(l.common_badges)
    server_badges.extend(l.server_badges)
    electrical_badges.extend(l.electrical_badges)
    garage_badges.extend(l.garage_badges)
    blacklisted_badges.extend(l.blacklisted_badges)

    ad_string = l.ad_string
    ad_address = l.ad_address
    ad_user = l.ad_user
    ad_password = l.ad_password
