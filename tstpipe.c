
#include <math.h>
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
   int pipe,i;

   // open a named pipe
   pipe = open("/tmp/population", O_WRONLY);
   if(pipe<0)
       perror("pipe");
   // get a line to send
//   printf("Enter line: ");
//   fgets(line, MAX_LINE, stdin);

   for(i=0; i<500; i++){
       sprintf(line,"%g\n",100*sin(8*i));
       write(pipe, line, strlen(line));
       fprintf(stderr,"Wrote---%s",line);
   }

	// close the pipe
   close(pipe);
   return 0;
}
