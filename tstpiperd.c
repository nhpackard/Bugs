
#include <sys/types.h>
#include <sys/stat.h>
#include <unistd.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <errno.h>

#define MAX_LINE 80

int main(int argc, char** argv) {
   char line[MAX_LINE];
   int pipe,i,tst,idx;
   char ch;

   // open a named pipe
   pipe = open("/tmp/population", O_RDONLY);

   // get a line to send
//   printf("Enter line: ");
//   fgets(line, MAX_LINE, stdin);

   tst=1;
   while(1){
       ch=0;
       idx=0;
       while(ch != '\n'){
           tst = read(pipe, &ch,1);
           if(tst<=0)
               exit(1);
           line[idx++]=ch;
       }
       line[idx]=0;
       fprintf(stderr,"From pipe got ---%s",line);
   }

	// close the pipe
   close(pipe);
   return 0;
}
