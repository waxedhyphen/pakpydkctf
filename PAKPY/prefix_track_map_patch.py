import anim_track_skel_map_patch as m

def install(App):
    old=m._targets_for_group
    def f(skel,count):
        t,mode=old(skel,count)
        if t:
            return t,mode
        b=m._bone_targets(skel)
        n=m._node_targets(skel)
        if count and b and count<=len(b):
            return b[:count],'skin_bone_prefix_order'
        if count and n and count<=len(n):
            return n[:count],'node_prefix_order'
        return t,mode
    m._targets_for_group=f
