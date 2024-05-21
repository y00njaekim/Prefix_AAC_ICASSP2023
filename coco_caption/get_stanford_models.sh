#!/usr/bin/env sh
# This script downloads the Stanford CoreNLP models.

CORENLP=stanford-corenlp-latest
SPICELIB=pycocoevalcap/spice/lib
JAR=stanford-corenlp-4.5.7

DIR="$( cd "$(dirname "$0")" ; pwd -P )"
cd $DIR

if [ -f $SPICELIB/$JAR.jar ]; then
  echo "Found Stanford CoreNLP."
else
  echo "Downloading..."
  wget http://huggingface.co/stanfordnlp/CoreNLP/resolve/main/$CORENLP.zip
  echo "Unzipping..."
  unzip $CORENLP.zip -d $SPICELIB/
  mv $SPICELIB/$JAR/$JAR.jar $SPICELIB/
  mv $SPICELIB/$JAR/$JAR-models.jar $SPICELIB/
  rm -f $CORENLP.zip
  rm -rf $SPICELIB/$CORENLP/
  echo "Done."
fi
