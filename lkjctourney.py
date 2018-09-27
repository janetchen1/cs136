#!/usr/bin/python

# This is a dummy peer that just illustrates the available information your peers 
# have available.

# You'll want to copy this file to AgentNameXXX.py for various versions of XXX,
# probably get rid of the silly logging messages, and then add more logic.

import random
import logging
from datetime import datetime

from messages import Upload, Request
from util import even_split
from peer import Peer

class LkjcTourney(Peer):
    def post_init(self):
        print "post_init(): %s here!" % self.id
        self.dummy_state = dict()
        self.dummy_state["cake"] = "lie"
        self.gamma = 0.1
        self.r = 3
        self.alpha = 0.2
        self.cap = self.up_bw
        self.flows = dict()
        self.taus = dict()
        self.unchoked_past = dict()
    
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


        logging.debug("%s here: still need pieces %s" % (
            self.id, needed_pieces))

        logging.debug("%s still here. Here are some peers:" % self.id)
        for p in peers:
            logging.debug("id: %s, available pieces: %s" % (p.id, p.available_pieces))

        logging.debug("And look, I have my entire history available too:")
        logging.debug("look at the AgentHistory class in history.py for details")
        logging.debug(str(history))

        requests = []   # We'll put all the things we want here
        # Symmetry breaking is good...
        random.shuffle(needed_pieces)
        
        # Sort peers by id.  This is probably not a useful sort, but other 
        # sorts might be useful
        peers.sort(key=lambda p: p.id)
        # request all available pieces from all peers!
        # (up to self.max_requests from each)

        # rarest first strategy
        piece_peers = dict()
        n_requests = dict()

        for peer in peers:
            av_set = set(peer.available_pieces)
            isect = av_set.intersection(np_set)
            n_requests[peer.id] = 0
            # n = min(self.max_requests, len(isect))
            for piece_id in list(isect):
                if piece_id not in piece_peers:
                    piece_peers[piece_id] = [peer]
                else:
                    piece_peers[piece_id].append(peer)

        # sort pieces by rarest
        rarest = sorted(piece_peers, key=lambda k: len(piece_peers[k]), reverse=False)
        for piece in rarest:
            for peer in piece_peers[piece]:
                if n_requests[peer.id] < self.max_requests:
                    n_requests[peer.id] += 1
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
        # One could look at other stuff in the history too here.
        # For example, history.downloads[round-1] (if round != 0, of course)
        # has a list of Download objects for each Download to this peer in
        # the previous round.

         # Initialize f_j and t_j for all peers
        if round == 0:
            for peer in peers:
                self.flows[peer.id] = self.up_bw / 4
                self.taus[peer.id] = 1
                # how many times has this peer unchoked me before?
                self.unchoked_past[peer.id] = 0

        chosen = []
        bws = []
        if len(requests) == 0:
            logging.debug("No one wants my pieces!")
        else:
            request_ids = []
            for request in requests:
                request_ids.append(request.requester_id)

            # step 4
            # sort peers by decreasing ratio of reciprocation likelihood
            ratios = dict()
            for peer in request_ids:
                ratios[peer] = self.flows[peer]/self.taus[peer]

            # assign "importance" indexes to peers based on how many pieces they have that I need
            needed = lambda i: self.pieces[i] < self.conf.blocks_per_piece
            needed_pieces = filter(needed, range(len(self.pieces)))
            np_set = set(needed_pieces)  # sets support fast intersection ops.

            peer_need_overlap = dict()

            for peer in peers:
                if peer in request_ids:
                    av_set = set(peer.available_pieces)
                    isect = av_set.intersection(np_set)
                    peer_need_overlap[peer] = len(list(isect))

            importance = sorted(peer_need_overlap, key=lambda k: peer_need_overlap[k])

            # pick uploads
            ul = 0
            sorted_peers = sorted(ratios, key=lambda k: ratios[k], reverse=False)
            logging.debug(sorted_peers)
            random.seed(datetime.now())
            while ul < self.cap and len(sorted_peers) > 0:
                # randomly vary to sometimes choose "important" peers over most efficient
                if random.random() <= 0.02 * len(chosen) and len(importance) > 0:
                    candidate = importance.pop()
                    while candidate in chosen:
                        candidate = importance.pop()
                    # eliminate chance for redundancy
                else:
                    candidate = sorted_peers.pop()
                    while candidate in chosen:
                        candidate = sorted_peers.pop()
                if (ul + self.taus[candidate]) < self.cap:
                    chosen.append(candidate)
                    bws.append(self.taus[candidate])
                ul += self.taus[candidate]

            """
            logging.debug("Still here: uploading to a random peer")
            # change my internal state for no reason
            self.dummy_state["cake"] = "pie"
            """
            
        # create actual uploads out of the list of peer ids and bandwidths
        uploads = [Upload(self.id, peer_id, bw)
                   for (peer_id, bw) in zip(chosen, bws)]

        if round == 0:
            return uploads

        # Step 5

        # find peers who unchoked me and update
        unchokers = set()
        for dl in history.downloads[round-1]:
            # update flow with observed flow
            self.flows[dl.from_id] = dl.blocks
            unchokers.add(dl.from_id)
            # increment unchoked_past
            self.unchoked_past[dl.from_id] += 1
            # if peer j has unchoked i for each of last r rounds, then decrease tau_j
            if self.unchoked_past[dl.from_id] > self.r:
                self.taus[dl.from_id] *= (1-self.gamma)

        # update tau and unchoked_past peers who didn't unchoke me
        others = list(set(chosen)-unchokers)
        for j in others:
            self.taus[j] *= (1+self.alpha)
            self.unchoked_past[j] = 0
            
        return uploads
