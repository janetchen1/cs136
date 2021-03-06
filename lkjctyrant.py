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

class LkjcTyrant(Peer):
    def post_init(self):
        print "post_init(): %s here!" % self.id
        self.dummy_state = dict()
        self.dummy_state["cake"] = "lie"
        self.gamma = 0.1
        self.r = 2
        self.alpha = 0.3
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
                    # eliminate symmetry
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
        # One could look at other stuff in the history too here.
        # For example, history.downloads[round-1] (if round != 0, of course)
        # has a list of Download objects for each Download to this peer in
        # the previous round.

         # Initialize f_j and t_j for all peers
        if round == 0:
            for peer in peers:
                self.flows[peer.id] = self.up_bw / 4.0
                self.taus[peer.id] = self.up_bw / 4.0
                # how many times has this peer unchoked me before?
                self.unchoked_past[peer.id] = 0
        else:
            # Step 5
            # look at last round downloads
            dl_history = dict()
            for dl in history.downloads[round-1]:
                if dl.from_id not in dl_history:
                    dl_history[dl.from_id] = dl.blocks
                    self.unchoked_past[dl.from_id] += 1
                else:
                    dl_history[dl.from_id] += dl.blocks

            available_change = set()
            for peer in peers:
                if peer.id not in dl_history:
                    self.unchoked_past[peer.id] = 0
                    available_change.add(peer.id)

            # look at last round uploads
            ul_history = set()
            for ul in history.uploads[round-1]:
                ul_history.add(ul.to_id)

            # update peers who I unchoked last round
            for peer in list(ul_history):
                if peer not in dl_history:
                    self.taus[peer] = self.taus[peer]*(1+self.alpha)
                else:
                    self.flows[peer] = dl_history[peer]
                    if self.unchoked_past[peer] > self.r:
                        self.taus[peer] = self.taus[peer]*(1-self.gamma)

            # update taus for peer to back to normal level
            # if didn't upload to us
            # so taus don't sky rocket out of control
            for peer in peers:
                if peer.id not in ul_history:
                    if peer.id in available_change:
                        self.taus[peer.id] = self.cap/4.0

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

            # pick uploads
            ul = 0
            sorted_peers = sorted(ratios, key=lambda k: ratios[k], reverse=True)
            for best in sorted_peers:
                if (ul + self.taus[best]) <= self.cap:
                    chosen.append(best)
                    bws.append(self.taus[best])
                    ul += self.taus[best]

        # create actual uploads out of the list of peer ids and bandwidths
        uploads = [Upload(self.id, peer_id, bw)
                   for (peer_id, bw) in zip(chosen, bws)]

        return uploads
