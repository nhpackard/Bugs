
// A couple of functions for checking the consistency of UT hash tables.



#if 0
    // copy alive pointers to an array, because Alive might change during an update
    for(i=0,b=Alive; b != NULL; b=b->hh.next) {
        bpt[i++] = b;
    }
    if(i != nalive) 
        fprintf(stderr,"Got %d, expected %d\n",i,nalive);
    for(i=0;i<nalive;i++)
        sensemove(bpt[i]);
#endif


void chkAlive()
{              
    unsigned _bkt_i;                                                             
    unsigned _count, _bkt_count;                                                 
    char *_prev;                                                                 
    struct UT_hash_handle *_thha;                                                 
    if (Alive) {                                                                  
        _count = 0;                                                              
        for( _bkt_i = 0; _bkt_i < (Alive)->hha.tbl->num_buckets; _bkt_i++) {       
            _bkt_count = 0;                                                      
            _thha = (Alive)->hha.tbl->buckets[_bkt_i].hh_head;                      
            _prev = NULL;                                                        
            while (_thha) {                                                       
               if (_prev != (char*)(_thha->hh_prev)) {                            
                   fprintf(stderr,"invalid hh_prev %p, actual %pn",                  
                    _thha->hh_prev, _prev );                                      
               }                                                                 
               _bkt_count++;                                                     
               _prev = (char*)(_thha);                                            
               _thha = _thha->hh_next;                                             
            }                                                                    
            _count += _bkt_count;                                                
            if ((Alive)->hha.tbl->buckets[_bkt_i].count !=  _bkt_count) {          
               fprintf(stderr,"invalid bucket count %d, actual %dn",                 
                (Alive)->hha.tbl->buckets[_bkt_i].count, _bkt_count);              
            }                                                                    
        }                                                                        
        if (_count != (Alive)->hha.tbl->num_items) {                               
            fprintf(stderr,"invalid hha item count %d, actual %dn",                   
                (Alive)->hha.tbl->num_items, _count );                             
        }                                                                        
        /* traverse hha in app order; check next/prev integrity, count */         
        _count = 0;                                                              
        _prev = NULL;                                                            
        _thha =  &(Alive)->hha;                                                     
        while (_thha) {                                                           
           _count++;                                                             
           if (_prev !=(char*)(_thha->prev)) {                                    
              fprintf(stderr,"invalid prev %p, actual %pn",                          
                    _thha->prev, _prev );                                         
           }                                                                     
           _prev = (char*)ELMT_FROM_HH((Alive)->hha.tbl, _thha);                    
           _thha = ( _thha->next ?  (UT_hash_handle*)((char*)(_thha->next) +        
                                  (Alive)->hha.tbl->hho) : NULL );                 
        }                                                                        
        if (_count != (Alive)->hha.tbl->num_items) {                               
            fprintf(stderr,"invalid app item count %d, actual %dn",                  
                (Alive)->hha.tbl->num_items, _count );                             
        }                                                                        
    }                                                                            
} 
void chkDead()
{              
    unsigned _bkt_i;                                                             
    unsigned _count, _bkt_count;                                                 
    char *_prev;                                                                 
    struct UT_hash_handle *_thhd;                                                 
    if (Dead) {                                                                  
        _count = 0;                                                              
        for( _bkt_i = 0; _bkt_i < (Dead)->hhd.tbl->num_buckets; _bkt_i++) {       
            _bkt_count = 0;                                                      
            _thhd = (Dead)->hhd.tbl->buckets[_bkt_i].hh_head;                      
            _prev = NULL;                                                        
            while (_thhd) {                                                       
               if (_prev != (char*)(_thhd->hh_prev)) {                            
                   fprintf(stderr,"invalid hh_prev %p, actual %pn",                  
                    _thhd->hh_prev, _prev );                                      
               }                                                                 
               _bkt_count++;                                                     
               _prev = (char*)(_thhd);                                            
               _thhd = _thhd->hh_next;                                             
            }                                                                    
            _count += _bkt_count;                                                
            if ((Dead)->hhd.tbl->buckets[_bkt_i].count !=  _bkt_count) {          
               fprintf(stderr,"invalid bucket count %d, actual %dn",                 
                (Dead)->hhd.tbl->buckets[_bkt_i].count, _bkt_count);              
            }                                                                    
        }                                                                        
        if (_count != (Dead)->hhd.tbl->num_items) {                               
            fprintf(stderr,"invalid hhd item count %d, actual %dn",                   
                (Dead)->hhd.tbl->num_items, _count );                             
        }                                                                        
        /* traverse hhd in app order; check next/prev integrity, count */         
        _count = 0;                                                              
        _prev = NULL;                                                            
        _thhd =  &(Dead)->hhd;                                                     
        while (_thhd) {                                                           
           _count++;                                                             
           if (_prev !=(char*)(_thhd->prev)) {                                    
              fprintf(stderr,"invalid prev %p, actual %pn",                          
                    _thhd->prev, _prev );                                         
           }                                                                     
           _prev = (char*)ELMT_FROM_HH((Dead)->hhd.tbl, _thhd);                    
           _thhd = ( _thhd->next ?  (UT_hash_handle*)((char*)(_thhd->next) +        
                                  (Dead)->hhd.tbl->hho) : NULL );                 
        }                                                                        
        if (_count != (Dead)->hhd.tbl->num_items) {                               
            fprintf(stderr,"invalid app item count %d, actual %dn",                  
                (Dead)->hhd.tbl->num_items, _count );                             
        }                                                                        
    }                                                                            
} 
<
