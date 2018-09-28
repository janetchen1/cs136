#!/usr/bin/python

# This is a dummy peer that just illustrates the available information your peers 
# have available.

# You'll want to copy this file to AgentNameXXX.py for various versions of XXX,
# probably get rid of the silly logging messages, and then add more logic.

import random
import logging

from messages import Upload, Request
from util import even_split
from peer import Peer

class LkjcStd(Peer):
    def post_init(self):
        print "post_init(): %s here!" % self.id
        self.dummy_state = dict()
        self.dummy_state["cake"] = "lie"
        self.optimistic = None
    
    def requests(self, peers, history):
        """
        peers: available info about the peers (who has what pieces)
        history: what's happened so far as far as this peer can see

        returns: a list of Request() objects

        This will be called after update_pieces() with the most recent state.
        """
        needed = lambda i: self.pieces[i] < self.conf.blocks_per_piece
        needed_pieces = filter(needed, range(len(self.pieces)))
        np_set = set(needed_pieces)  # sets support fast intersection ops.

        requests = []   # We'll put all the things we want here
        # Symmetry breaking is good...
        random.shuffle(needed_pieces)

        # request all available pieces from all peers!
        # (up to self.max_requests from each)

        # rarest first strategy
        piece_peers = dict()
        piece_counts = dict()
        n_requests = dict()

        for peer in peers:
            av_set = set(peer.available_pieces)
            isect = av_set.intersection(np_set)
            n_requests[peer.id] = 0
            # n = min(self.max_requests, len(isect))
            for piece_id in list(isect):
                if piece_id not in piece_peers:
                    piece_peers[piece_id] = [peer.id]
                    piece_counts[piece_id] = 0
                else:
                    piece_peers[piece_id].append(peer.id)
                    piece_counts[piece_id] += 0

        counts_piece = dict()
        for piece, count in piece_counts.items():
            if count in counts_piece:
                counts_piece[count].append(piece)
            else:
                counts_piece[count] = [piece]

        rarest = sorted(counts_piece.items())


        for peer in peers:
            av_set = set(peer.available_pieces)
            isect = av_set.intersection(np_set)
            n = min(self.max_requests, len(isect))
            count = 0
            while count < n:
                for c, piece_id_list in rarest:
                    random.shuffle(piece_id_list)
                    for piece_id in piece_id_list:
                        if piece_id in av_set:
                            count += 1
                            start_block = self.pieces[piece_id]
                            r = Request(self.id, peer.id, piece_id, start_block)
                            requests.append(r)

        return requests

    def uploads(self, requests, peers, history):
        """
        requests -- a list of the requests for this peer for this round
        peers -- available info about all the peers
        history -- history for all previous rounds

        returns: list of Upload objects.

        In each round, this will be called after requests().
        """

        round = history.current_round()
        logging.debug("%s again.  It's round %d." % (
            self.id, round))

        if len(requests) == 0:
            logging.debug("No one wants my pieces!")
            chosen = []
            bws = []
        else:
            chosen = []
            # if insufficient history, optimistically unchoke for all 3 meritocratic slots
            if history.current_round < 2:
                options = requests
                for i in range(3):
                    choice = random.choice(options)
                    options.remove(choice)
                    chosen.append(choice)
            else:
                # list of requesters
                requesters = []
                for request in requests:
                    requesters.append(request.requester_id)

                # aggregate downloads from last 2 rounds to reference later
                download_history = {}
                for dl in history.downloads[round-1]:
                    if dl.from_id in requesters:
                        # disregard peers who aren't requesting
                        if dl.from_id in download_history:
                            download_history[dl.from_id] += dl.blocks
                        else:
                            download_history[dl.from_id] = dl.blocks

                # unchoke those who gave you fastest download speeds in last 2 rounds combined
                for i in range(3):
                    if len(download_history) > 0:
                        top = max(download_history, key=download_history.get)
                        #argmax((k, download_history[k]) for k in download_history.keys())
                        chosen.append(top)
                        download_history.pop(top, None)
                        requesters.remove(top)

                # optimistic unchoke - 1 new one every 3 rounds
                if round % 3 == 0:
                    if len(requesters) > 0:
                        self.optimistic = random.choice(requesters)
                chosen.append(self.optimistic)
            
            # Evenly "split" my upload bandwidth among the chosen requesters
            bws = even_split(self.up_bw, len(chosen))

        # create actual uploads out of the list of peer ids and bandwidths
        uploads = [Upload(self.id, peer_id, bw)
                   for (peer_id, bw) in zip(chosen, bws)]
            
        return uploads
