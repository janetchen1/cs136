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

class LkjcPropShare(Peer):
    def post_init(self):
        print "post_init(): %s here!" % self.id
        self.dummy_state = dict()
        self.dummy_state["cake"] = "lie"
        self.percentage = 0.9
    
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

        chosen = []
        bws = []
        if len(requests) == 0:
            logging.debug("No one wants my pieces!")
        else:
            if round == 0:
                chosen = [request.requester_id for request in requests]
                bws = even_split(self.up_bw, len(chosen))
            else:
                requester_ids = [request.requester_id for request in requests]
                # requester_id : blocks given to us in last round
                last_dls = {}
                # find peers who unchoked me and update
                for dl in history.downloads[round-1]:
                    # update peer with observed flow from peer if peer is a requester
                    if dl.from_id in requester_ids:
                        last_dls[dl.from_id] = dl.blocks

                # smallest to largest
                sorted_ids = sorted(last_dls, key=lambda k: last_dls[k], reverse=False)
                #if len(sorted_ids) > 3:
                #    sorted_ids = sorted_ids[:2]
                total_dl = sum([last_dls[k] for k in sorted_ids])

                for chosen_peer in sorted_ids:
                    chosen.append(chosen_peer)
                    ratio = float(last_dls[chosen_peer])/float(total_dl)
                    bw = ratio*self.percentage*self.up_bw
                    bws.append(bw)

                others = list(set(requester_ids) - set(sorted_ids))
                if len(others) > 0:
                    optimistic = random.choice(others)
                    chosen.append(optimistic)
                    bws.append(self.up_bw-sum(bws))

        # create actual uploads out of the list of peer ids and bandwidths
        uploads = [Upload(self.id, peer_id, bw)
                   for (peer_id, bw) in zip(chosen, bws)]
            
        return uploads
