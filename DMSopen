#!/bin/bash

###
### parse arguments with getopt
###

getopt --test > /dev/null
if [[ $? -ne 4 ]]; then
    echo "I’m sorry, `getopt --test` failed in this environment."
    exit 1
fi

SHORT=d:b:p:
LONG=door:,badge:,pin:

# -temporarily store output to be able to check for errors
# -activate advanced mode getopt quoting e.g. via “--options”
# -pass arguments only via   -- "$@"   to separate them correctly
PARSED=`getopt --options $SHORT --longoptions $LONG --name "$0" -- "$@"`
if [[ $? -ne 0 ]]; then
    # e.g. $? == 1
    #  then getopt has complained about wrong arguments to stdout
    exit 2
fi
# use eval with "$PARSED" to properly handle the quoting
eval set -- "$PARSED"

# now enjoy the options in order and nicely split until we see --
while true; do
    case "$1" in
        -d|--door)
            door="$2"
            shift 2
            ;;
        -b|--badge)
            badge="$2"
            shift 2
            ;;
        -p|--pin)
            pin="$2"
            shift 2
            ;;
        --)
            shift
            break
            ;;
        *)
            echo "Programming error"
            exit 3
            ;;
    esac
done


###
### done parsing arguments; now do stuff
###

if [[ $badge ]]; then
	json_string="{\"door\":\"${door}\", \"badge\":\"${badge}\"}"
elif [[ $pin ]]; then
	json_string="{\"door\":\"${door}\", \"pin\":\"${pin}\"}"
fi

echo $json_string
echo $json_string > /dev/udp/127.0.0.1/6666
